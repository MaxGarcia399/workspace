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
  mono/                 ← B/N de alto contraste; olympo vive EMBEBIDO en
    theme.json             los motores (hubtheme._FALLBACK / tuitheme._OLYMPO),
    web.css                ya sin carpeta (poda 2026-10-02)
  cyberpunk/            ← skin completo (tokens + layout + animación),
    theme.json             retuneado 2026-10-02: neones a tono joya
    web.css
  rose/ durazno/ lavanda/ salvia/ bruma/   ← la familia rosé (acento pastel
    theme.json                                sobre carbón; bruma = DEFAULT del hub)
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
olympo, papel, slate, bosque — un id de esos guardado en config cae a `bruma`.

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
  "tui": { … },                 // paleta ANSI del recinto — ver sección TUI
  "palette": { … }              // paleta SEMÁNTICA (opcional) — fuente de las
                                //  plantillas; ver "Paleta semántica" abajo
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
2. El store unificado — DOS ajustes independientes:
   - `ui.theme` = el **hub/TUI** (`python3 settings.py set ui.theme <id>`, el
     menú **Config › Tema del hub**, el pin del hub, el onboarding);
   - `ui.web_theme` = el **dev panel web** (su switcher, `POST /api/theme`).
3. Default — **uno por superficie, y uno solo en código**:
   - hub/TUI: **`bruma`** = `tuitheme.DEFAULT_ID` = default de `ui.theme` en
     `settings.py` (lo que ve una instalación nueva). Un id guardado que ya no
     existe en `themes/` también cae a `bruma`.
   - dev panel: `olympo` = `hubtheme.DEFAULT_ID` (el `:root` del shell, sin
     overrides — herramienta de equipo, no viaja a clientes).

Falla-suave absoluta: un id inexistente se salta al siguiente candidato (y al
final al default); un manifiesto corrupto o una clave inválida → el valor del
dorado embebido (`olympo`) para esa clave. El TUI jamás se rompe por un tema.
`tests/test_theme_render.py` vigila que código, settings y este README digan
el mismo default.

## Paleta semántica: una fuente, todas las superficies (`theme_render.py`)

Un tema puede declarar un bloque **`palette`** (ADITIVO, opcional) con colores
con nombre; de ahí salen, por **plantilla** (`templates/theme/*.json.tpl`), el
bloque `tui`, los `web.tokens`, el fondo/tinta OSC de la terminal y el tema
DENTRO de cada motor:

```jsonc
"palette": {
  "background": "#161a21", "foreground": "#e1e7f0", "accent": "#a9bfdd",
  "accent_2": "#c9a9ba",   "muted": "#9fabc0",     "faint": "#6a7488",
  "surface": "#1c212a",    "border": "#303948",    "cursor": "#a9bfdd",
  "success": "#8fc3a8",    "warning": "#dcba84",   "danger": "#dd7d88",
  "info": "#8fb8d8"        // todo opcional: lo ausente se deriva por mezcla
}
```

- **Un tema nuevo puede ser SOLO `palette`**: tuitheme y hubtheme le generan
  `tui` y `web.tokens`. Si además trae `tui`/`web.tokens`, **lo explícito
  gana** clave a clave (lo hecho a mano manda).
- **Los temas existentes no cambian**: sin `palette`, tuitheme/hubtheme pintan
  exactamente lo de siempre. Su paleta (para plantillas de motor y para
  agentes que los referencian) se DERIVA de lo que ya declaran (`web.tokens`
  → `tui.osc` → `tui.roles` → `swatches`).
- Plantillas: `osc` · `tui` · `web` · `engine-<motor>`. Sintaxis mínima, sin
  lógica: `{{ clave }}`, `{{ mix a b 15% }}` (a mezclado 15% hacia b),
  `{{ alpha clave 0.12 }}` (rgba). Una plantilla que falla o no produce JSON
  NO escribe nada.
- **Motores** (`theme_render.ENGINES`): `claude-code` →
  `engine-claude-code.json.tpl` (el `~/.claude/themes/<n>.json` que se activa
  con `custom:<n>`). **Codex y Antigravity: hook vacío a propósito** — su
  formato de tema in-app no está documentado/verificado; esos motores reciben
  solo los colores de terminal (OSC), que sirven con cualquier CLI.
  **Agregar un motor = dropear su plantilla y anotarla en `ENGINES`**, sin
  tocar ningún tema.
- **Agentes**: `agent_admin.write_agent_theme` renderiza el tema del agente
  (terminal + in-app) desde UNA paleta — la de su color, o la de un tema del
  hub con `hub_theme=<id>`. Una entrada de `themes.local.json` puede ser
  `{"theme": "<id>", "bg": …, "fg": …}`: `theme.py` hereda el fondo/tinta del
  tema del hub mientras exista (bg/fg = copia para versiones viejas y
  respaldo). Las paletas por agente de siempre (`themes.json`,
  `themes.local.json`, `themes-cc/<agente>.json`) siguen idénticas.
- **Escritura atómica**: `theme_render.stage_write` escribe todo a temporales
  y reemplaza de un golpe; si algo falla, lo anterior queda intacto.
- **Lo hecho a mano gana**: lo que generamos queda registrado (sha256) en
  `<estado>/theme-render.json`; si después editas el archivo (p. ej.
  `~/.claude/themes/<agente>.json` o `<estado>/themes-cc/<agente>.json`), ni la
  creación de agentes ni `install` lo vuelven a pisar. Un archivo de una versión
  anterior (sin registro) se presume generado y se actualiza como siempre.
- **Hook `theme-set`** (opcional): `<estado>/hooks/theme-set.py` (cualquier OS)
  o `theme-set` ejecutable (POSIX) / `theme-set.cmd|.bat` (Windows). Corre tras
  cada cambio de `ui.theme` con el id nuevo como argumento, sin bloquear el
  hub, muerto a los 10 s; si falla no pasa nada. Apagarlo:
  `WORKSPACE_NO_THEME_HOOK=1`.
- Presets de prueba `prueba`/`midas`/`midas2` salieron de `themes.json` (eran
  agentes de prueba colados antes de que los temas de agente fueran
  per-máquina). Si una máquina tiene un agente con ese nombre,
  `theme_render.adopt_legacy_presets(nombres)` copia su paleta a
  `themes.local.json` (idempotente; pensado para el runner de migraciones).

```bash
python3 theme_render.py bruma                     # paleta semántica derivada
python3 theme_render.py bruma engine-claude-code  # render de una plantilla
```

## Probar un tema

```bash
python3 hubtheme.py            # lista temas + activo
python3 hubtheme.py <id>       # dump del CSS que emite
WORKSPACE_THEME=<id> workspace dev # el panel con ese tema (sin persistir)
```

Suite relacionada: `tests/test_theme_engine.py`.
