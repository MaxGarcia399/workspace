{
  "name": "{{ name }}",
  "settings": [
    {
      "settings": {
        "background": "{{ background }}",
        "foreground": "{{ foreground }}",
        "caret": "{{ cursor }}",
        "selection": "{{ mix background accent 30% }}",
        "lineHighlight": "{{ surface }}",
        "gutter": "{{ background }}",
        "gutterForeground": "{{ faint }}",
        "invisibles": "{{ faint }}"
      }
    },
    {"name": "Barra · modelo", "scope": "entity.name.type, support.type, support.class, entity.name.class",
     "settings": {"foreground": "{{ accent }}"}},
    {"name": "Barra · contexto", "scope": "constant, constant.numeric, constant.language, constant.character",
     "settings": {"foreground": "{{ accent_2 }}"}},
    {"name": "Barra · límites", "scope": "keyword.operator",
     "settings": {"foreground": "{{ accent_hi }}"}},
    {"name": "Barra · permisos", "scope": "keyword, storage, storage.modifier, storage.type",
     "settings": {"foreground": "{{ accent_hi }}"}},
    {"name": "Comentarios", "scope": "comment, punctuation.definition.comment",
     "settings": {"foreground": "{{ muted }}", "fontStyle": "italic"}},
    {"name": "Cadenas · barra: proyecto", "scope": "string, markup.inline.raw, markup.raw",
     "settings": {"foreground": "{{ success }}"}},
    {"name": "Funciones", "scope": "entity.name.function, support.function, meta.function-call",
     "settings": {"foreground": "{{ info }}"}},
    {"name": "Parámetros", "scope": "variable.parameter",
     "settings": {"foreground": "{{ warning }}"}},
    {"name": "Etiquetas", "scope": "entity.name.tag",
     "settings": {"foreground": "{{ accent }}"}},
    {"name": "Atributos", "scope": "entity.other.attribute-name",
     "settings": {"foreground": "{{ accent_2 }}"}},
    {"name": "Títulos", "scope": "markup.heading, entity.name.section",
     "settings": {"foreground": "{{ accent }}", "fontStyle": "bold"}},
    {"name": "Enlaces", "scope": "markup.underline.link",
     "settings": {"foreground": "{{ info }}"}},
    {"name": "Diff · agregado", "scope": "markup.inserted, meta.diff.header.to-file",
     "settings": {"foreground": "{{ success }}"}},
    {"name": "Diff · quitado", "scope": "markup.deleted, meta.diff.header.from-file",
     "settings": {"foreground": "{{ danger }}"}},
    {"name": "Diff · cambiado", "scope": "markup.changed",
     "settings": {"foreground": "{{ warning }}"}},
    {"name": "Inválido", "scope": "invalid",
     "settings": {"foreground": "{{ danger }}"}}
  ]
}
