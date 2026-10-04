# themes/ — temas del harness (motor: `hubtheme.py`)

Un **tema** re-tematiza las superficies de WORKSPACE: el dev panel **web**
(`hubtheme.py`, bloque `web`) y el **TUI** del recinto — `front.py`, banner y
config (`tuitheme.py`, bloque `tui`). La arquitectura completa vive en la rama
`design/temas-propuestas` → `research/design/temas/ARQUITECTURA.md`; F1 =
tokens web + registro + selección a nivel harness; F3-F4 = el TUI (este dir
ya las incluye).

## Un tema = un directorio (auto-descubierto)

```
themes/
  mono/                 ← default del HUB (ui.theme); olympo vive EMBEBIDO en
    theme.json             los motores (hubtheme._FALLBACK / tuitheme._OLYMPO),
    web.css                ya sin carpeta (poda 2026-10-02)
  cyberpunk/            ← skin completo (tokens + layout + animación),
    theme.json             retuneado 2026-10-02: neones a tono joya
    web.css
  rose/ durazno/ lavanda/ salvia/ bruma/   ← la familia rosé (acento pastel
    theme.json                                sobre carbón; rose = referencia)
    web.css
  oficina-8bit/ observatorio/ estudio/   ← skins de mockup (solo dev panel;
    theme.json                              estudio = tema CLARO)
    web.css
  zenith/ carmesi/ argus/   ← solo-tokens (re-acentúan el DS, nada más)
    theme.json
```

El switcher del HUB (ui.theme) está curado a `settings._TUI_THEMES` =
mono · cyberpunk · rose · durazno · lavanda · salvia · bruma (sincronizada
con `hubtheme.TUI_PENDIENTES`). Temas borrados en la poda 2026-10-02:
olympo, papel, slate, bosque — un id de esos guardado en config cae a `mono`.

**Agregar un tema = dropear `themes/<id>/theme.json`** (y opcional `web.css`).
Sin tocar `hubtheme.py`, `dashboard.py` ni el shell — se descubre solo, igual
que las secciones de `dash/dev/`. Quitar un tema = borrar su carpeta (el motor
cae al default, falla-suave).

## `theme.json` — el manifiesto

```jsonc
{
  "id": "mi-tema",              // = nombre del dir ([a-z0-9-_]); el dir manda
  "label": "Mi Tema",           // nombre visible en el switcher
  "emoji": "✦",                 // opcional
  "swatches": ["#c1", "#c2"],   // 2 muestras del switcher (opcional: se derivan
                                //  de accent / accent-2)
  "web": {
    "tokens": { … },            // ver tabla — TODO opcional, fallback al :root
    "css": "web.css"            // skin opcional (nombre de archivo en este dir)
  },
  "tui": { … }                  // paleta ANSI del recinto — ver sección TUI
}
```

### Tokens (`web.tokens`) — claves conocidas

Cada token se emite como `--th-<clave>` scoped a `body[data-theme="<id>"]` y
re-liga el alias `--ds-*` que TODO el panel consume. Claves desconocidas se
emiten como `--th-<clave>` a secas (p. ej. `accent-2`).

| token | alias DS | qué pinta |
|---|---|---|
| `bg` `surface` `surface2` `surface3` | `--ds-bg` `--ds-surface` `--ds-surface-2/-3` | fondos por elevación |
| `border` `border-hi` | `--ds-border(-hi)` | bordes |
| `text` `dim` `faint` | `--ds-text/dim/faint` | jerarquía de texto |
| `accent` `accent-hi` `accent-soft` `accent-line` | `--ds-gold*` | el acento (el "dorado" del DS) |
| `red` `amber` `blue` `green` `grey` | `--ds-<color>` | semánticos (error/warn/ok…) |
| `radius` `radius-sm` | `--ds-radius(-sm)` | redondez |
| `fast` `med` | `--ds-fast/med` | velocidad de transición |
| `sp-1`…`sp-5` | `--ds-sp-*` | espaciado |
| `font` | (solo `--th-font`) | tipografía del panel |

### Skin (`web.css`) — capas L (layout) y A (animación)

- **TODO scoped** a `body[data-theme="<id>"]` — dos temas jamás se pisan.
- **El DOM no cambia por tema, SOLO CSS** (regla de oro): las secciones
  (`board.js`, `versiones.js`…) siguen montando el mismo HTML. Selectores
  disponibles: `.shell .side .brand .nav .navitem .hdr .content .palbtn`,
  primitivas `.ds-*`, `dev-flash`, `dev-busy`.
- Animaciones: `@keyframes` propios (prefijo del tema, ej. `cyb-*`). Respetar
  `prefers-reduced-motion` y `body[data-anim="off"]`.
- Nada de assets externos: CSS autocontenido (data-URIs si hace falta).

### Bloque `tui` — paleta ANSI del recinto (motor: `tuitheme.py`)

El MISMO tema pinta el TUI (`front.py` + `banner/render.py` + `config_tui.py`).
Colores: `"#rrggbb"` (truecolor → cuantizado a 256 → 16 según la terminal) o
un **entero 0-255** = índice xterm-256 EXACTO (jamás se re-cuantiza — así
olympo garantiza paridad). `NO_COLOR`/`TERM=dumb` → sin ANSI; override de
prueba: `WORKSPACE_COLOR=mono|16|256|truecolor`. TODO opcional — cada clave
ausente/inválida cae a la de olympo (falla-suave por clave).

```jsonc
"tui": {
  "roles": {                    // los papeles históricos del recinto
    "text": "#…",  "hi": "#…",  "accent": "#…", "mid": "#…",
    "dim": "#…",   "dark": "#…", "grey": "#…",
    "inactive": "#…", "inactive_alt": "#…",
    "err": "#…", "ok": "#…", "bad": "#…"
  },
  "stars":   { "dim": ["#…"], "mid": ["#…"], "hi": "#…" },  // el cielo
  "fire":    ["#…"],            // gradiente de la llama (oscuro → punta)
  "ember":   ["#…"],            // brasas de urna apagada
  "off":     "#…",              // metal de urna apagada
  "wordmark": ["mid","mid","accent","accent","hi","hi"],  // 6 filas (rol o color)
  "glyphs": {                   // opcionales; angostos-seguros (Windows)
    "box": "╔╗╚╝║═",            // 6 chars: esquinas + bordes de la caja
    "pointer": "►", "bracket_l": "◄", "bracket_r": "►",
    "orn": "■", "sep": "═", "base": "▄",
    "star_d": ["·","+"], "star_h": ["+","*"]   // glifos del cielo
  },
  "osc": { "bg": "#…", "fg": "#…", "cursor": "#…" }  // fondo/tinta de la
                                 // terminal (OSC 10/11/12) — así `estudio`
                                 // logra su papel CLARO
}
```

Restricción de oro del recinto: los temas solo cambian **paleta y glifos** —
el cielo sigue ESTÁTICO y la fórmula de pantalla de `front.py` no se toca
(nada de animación full-screen: rompe teclado/resize en Mac).

## Selección (precedencia env > store > default)

1. `WORKSPACE_THEME=<id>` (env — gana siempre; ideal para probar).
2. `ui.theme` en el store unificado: `python3 settings.py set ui.theme <id>`,
   el menú **Config › Tema del harness** del recinto, o el **switcher del dev
   panel** (persiste vía `POST /api/theme`, guard Y1).
3. Default: `olympo`.

Web y TUI leen el MISMO id — cambiar el tema en el panel también re-tematiza
el recinto en el siguiente arranque (`workspace`).

Falla-suave absoluta: id inexistente o manifiesto corrupto → `olympo`.

## Probar un tema

```bash
python3 hubtheme.py            # lista temas + activo
python3 hubtheme.py <id>       # dump del CSS que emite
WORKSPACE_THEME=<id> workspace dev # el panel con ese tema (sin persistir)
```

Suite relacionada: `tests/test_theme_engine.py`.
