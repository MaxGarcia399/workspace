# i18n de Workspace — cómo traducir una pantalla (fases 1+)

**Qué es esto.** La capa de internacionalización del lado **cliente**. FASE 0
dejó la fundación: el módulo `i18n.py`, los catálogos `lang/<code>.py`, el
**cuadro IDIOMA** del hub (layout `dia`, bajo PERSONALIZACIÓN) y el idioma como
paso 0 del onboarding, con 3 pantallas de prueba ya traducidas (menú del hub,
bienvenida del onboarding, greeter de agente). Las fases siguientes **traducen
pantalla por pantalla** siguiendo este patrón — este doc es el contrato.

## Regla de oro (alcance)

Solo se traduce **lo que ve el cliente**. Las pantallas/comandos de
**desarrollo** (gateados por `front._has_dev_panel()` / `dev_tui.is_dev()`,
stripeados del distro) **se quedan en español** — no las toques. Ejemplo ya
aplicado: la entrada «Dev» del menú (`__devmap__`) NO pasa por `t()`.

## Estructura (paquetes por pantalla)

Los catálogos son **sub-paquetes por idioma con un módulo por pantalla**:

```
lang/
  es/                 ← FUENTE (español)        en/                 ← traducción
    common.py              hub.py                 common.py  hub.py
    tono.py  calendario.py  github.py             tono.py    …
    addagent.py  actualizaciones.py  atajos.py
    personalizacion.py  onboarding.py  greeter.py  banner.py
```

Cada módulo exporta `STRINGS = {...}` con claves namespaceadas por esa pantalla.
`i18n` **descubre y mergea** todos los `lang/<code>/*.py` en un solo dict
(falla-suave por módulo: uno roto/ausente no tumba al resto). Añadir un idioma =
crear `lang/<code>/` con los mismos módulos. Añadir una pantalla nueva = un
módulo nuevo en `es/` y `en/`.

> **Por qué paquetes y no un `es.py` plano:** el fan-out de traducción asigna
> **UN agente por pantalla** → cada uno toca solo `lang/es/<pantalla>.py` +
> `lang/en/<pantalla>.py`, sin pisarse entre sí (cero colisiones de merge).

## El modelo

- **`es` es la FUENTE y el default.** Cada cadena en `lang/es/<pantalla>.py` es
  el texto español EXACTO que el harness mostraba hardcodeado. Sin `ui.lang`
  guardado y sin `WORKSPACE_LANG`, todo se ve idéntico a siempre.
- **Falla-suave en cascada.** `t(key)` busca en el idioma activo → si falta, en
  `es` → si falta, devuelve la propia `key`. Una pantalla a medio traducir
  degrada a español, nunca crashea ni muestra una clave cruda... salvo que te
  olvides de agregarla a `es` (ver checklist).
- **Idioma activo** (`i18n.lang()`): `WORKSPACE_LANG` (env, gana) →
  `settings ui.lang` → `"es"`. Se resuelve en vivo (cacheado, invalidado al
  guardar), igual que el tema se re-resuelve por tick.

## Cómo agrego una cadena traducible — 4 pasos

1. **Elige una clave namespaced por pantalla.** Convención:
   `"<pantalla>.<sub>.<rol>"`. Ejemplos vivos: `"menu.github.label"`,
   `"menu.github.tag"`, `"onboarding.welcome.p1"`, `"greeter.sessions.title"`,
   `"onboarding.hints.idioma"`. Agrupa por pantalla; usa `label`/`tag`/`title`/
   `hint`/`p1`/`body` como sufijos de rol. La clave va en **tu** módulo
   (`lang/es/<pantalla>.py`), no en otro.

2. **Copia el literal español TAL CUAL a `lang/es/<pantalla>.py`** bajo esa
   clave. No lo reescribas: debe ser byte-idéntico a lo que mostraba el código
   (así el default no cambia para nadie).

3. **Agrega la MISMA clave a `lang/en/<pantalla>.py`** con la traducción. (Toda
   clave de `es` debería existir en `en`; el objetivo de cada fase es dejar su
   pantalla completa.)

4. **Reemplaza el literal en el código por `i18n.t("clave")`.** Dos patrones:

   **Patrón A — import directo** (módulos que corren desde la raíz del harness,
   p. ej. `front.py`, `onboarding_tui.py`):
   ```python
   import i18n
   ...
   etiqueta = i18n.t("menu.cal.label")
   ```

   **Patrón B — con red de seguridad inline** (módulos que pueden correr donde
   la raíz no está en `sys.path`, p. ej. `agent_ui.py` lo delegan dashboards
   desde el `brand/` del cerebro). Define un `_t(key, es)` local que cae al
   español inline si `i18n` no se pudo importar:
   ```python
   try:
       import i18n
   except Exception:
       i18n = None

   def _t(key, es):
       if i18n is None:
           return es
       try:
           s = i18n.t(key)
           return s if s != key else es
       except Exception:
           return es
   ...
   titulo = _t("greeter.sessions.title", "SESIONES")
   ```
   El `es` inline es idéntico al valor del catálogo `es` → doble garantía de
   paridad.

### Interpolación

`t("clave", nombre=...)` aplica `.format(**kw)` sobre la cadena. En el catálogo
usa llaves con nombre: `"saludo": "hola {quien}"`. Falla-suave: si el `format`
truena (kw faltante), devuelve la cadena cruda, sin excepción.

## La REGLA DE ANCHO (crítica en el TUI)

Las frases en inglés **miden distinto** que en español, y el TUI es sensible al
ancho. Antes de dar por traducida una pantalla:

- **Renderiza headless con `WORKSPACE_LANG=en` a anchos 130 / 100 / 80** y
  confirma que ninguna línea excede `w-1` (el hub clipa/cede, nunca desborda).
  Patrón de verificación (ver `tests/test_i18n.py::test_render_idioma_no_overflow_en`):
  ```python
  import re, hublayout as HL
  vis = HL.vis(re.sub(r"\x1b\[[0-9;]*m", "", linea))
  assert vis <= w - 1
  ```
- Las cajas ya envuelven el texto (`_wrap`/`UI.box`/`H.clip`); lo que debes
  cuidar son **títulos, labels de una línea y hints del pie** — ahí el inglés
  más largo puede empujar. Si no cabe, acorta la traducción (no el layout).
- El `keyline` del hub ya **descarta pares que no caben**: es comportamiento
  esperado, no un bug de tu traducción.

## Cómo cambia el idioma el usuario

- **Cuadro IDIOMA del hub** (layout `dia`, bajo PERSONALIZACIÓN): las dos
  opciones ES/EN visibles con la activa marcada `●`; se navega como tema/fondo
  (↑↓ entra a la sección, ◄► mueve el cursor, Enter aplica). Al elegir:
  `i18n.set_lang` + flip EN VIVO de todo el hub. Es una SECCIÓN navegable
  (grupo `idioma` en front.py), NO una entrada del menú; el layout la declara
  con `"idioma": True` en su registro (igual que `"cal"`), así `clasico`/
  `centro` no ganan una sección fantasma. El cuadro lo dibuja
  `hublayout._dia_idioma_body`.
- **Onboarding, paso 0:** elige idioma antes de la bienvenida; el resto del
  flujo ya sale en ese idioma.
- **Config / CLI:** `settings set ui.lang en` · `python3 i18n.py set en`.
- **Prueba sin persistir:** `WORKSPACE_LANG=en workspace`.

> Para que el hub flipee EN VIVO al cambiar idioma, lo que dependa del idioma y
> esté cacheado por sesión debe reconstruirse tras `set_lang`. Ejemplo:
> `front.apply_lang()` rebuilda las labels del MENÚ (`_LDATA["opts"]`) desde
> `menu_entries()` — los TOKENS no cambian con el idioma, solo las labels, así
> que jump/keybinds/selección siguen válidos. El cuadro IDIOMA y el greeter
> leen `i18n.lang()` en cada render, así que flipean solos.

## El fan-out: UN agente = UNA pantalla (sin colisiones)

Para traducir el harness entero sin que los agentes se pisen, el trabajo se
reparte **por pantalla**: cada agente toma UNA y toca SOLO sus dos módulos:

```
agente → pantalla → edita  lang/es/<pantalla>.py   (si faltara algún literal)
                    edita  lang/en/<pantalla>.py   (la traducción)
                    envuelve con t() los literales de ESA pantalla en el código
```

Módulos (pantallas) del reparto, con su archivo de código principal:

| módulo | pantalla / código |
|---|---|
| `hub` | recinto: menú + cuadro IDIOMA (`front.py`, `hublayout.py`) — **hecho** |
| `greeter` | saludo de agente (`agent_ui.py`) — **hecho** |
| `onboarding` | primer arranque (`onboarding_tui.py`) — **hecho (paso 0 + bienvenida)** |
| `tono` | diales de personalidad (`tono_tui.py`) |
| `calendario` | editor de agenda (`calendario_tui.py`) |
| `github` | repos/ramas/PRs (`github_tui.py`, `git_tui.py`) |
| `addagent` | crear/cargar agente, modelo/motor, banner (`add_agent_tui.py` y afines) |
| `actualizaciones` | revisar/reparar/actualizar (`actualizaciones_tui.py`) |
| `atajos` | re-mapear teclas (`keybinds_tui.py`) |
| `personalizacion` | labels de pins tema/fondo + fondo independiente |
| `common` | cadenas compartidas entre pantallas |
| `banner` | template de banner de agente |

Reglas que TODO agente del fan-out respeta (están arriba, se repiten por ser las
que más se rompen):
1. **ES-fuente / EN-traducción.** El literal español va TAL CUAL a `es/`; la
   traducción a `en/`. ES por default queda byte-idéntico.
2. **Regla de ancho.** El inglés mide distinto; renderizá la pantalla con
   `WORKSPACE_LANG=en` a **130/100/80** (y, si es del hub, en los layouts y la
   ventana alta) y confirmá que nada excede `w-1`.
3. **Solo cliente.** Las pantallas/comandos de **dev** (gate `_has_dev_panel`/
   `is_dev`, stripeadas del distro) se quedan en español — **fuera de alcance**.

Como cada quien edita módulos distintos, dos PRs del fan-out no chocan aunque
lleguen a la vez.

## Agregar un idioma nuevo (p. ej. `pt`)

1. `i18n._SUPPORTED` += `("pt", "Português")`.
2. `settings` → `ui.lang` `choices` += `"pt"`.
3. Crea el paquete `lang/pt/` con los mismos módulos que `lang/es/` (podés
   copiar la estructura y traducir módulo por módulo; los que falten caen a
   `es` solos).

## Checklist por pantalla (fases 1+)

- [ ] Claves namespaced, en `lang/es/<pantalla>.py` (literal exacto) **y**
      `lang/en/<pantalla>.py`.
- [ ] Literales del código reemplazados por `t()` / `_t()`.
- [ ] Solo cliente: ninguna pantalla/comando dev tocada.
- [ ] Render EN a 130/100/80 sin desbordes (y por layout si es del hub).
- [ ] `es` por default byte-idéntico a antes (sin `ui.lang`).
- [ ] Un test dirigido (lookup + no-overflow) en `tests/test_i18n.py` o vecino.

> La suite es DETERMINISTA respecto al idioma: `TempHomeCase` (base hermética)
> saca `WORKSPACE_LANG` del entorno y resetea los caches de `i18n`/`keybinds`,
> así que los tests de labels corren en `es` (el default del store temp) sin
> importar el idioma que tengas persistido en tu máquina. Si tu pantalla cachea
> algo dependiente del idioma al importar, exponé un `refresh()` como keybinds.

## Claves COMPARTIDAS de la Ola 1 (reusar, NO redefinir)

La Ola 1 tradujo TODO el «chrome» compartido del hub (layouts `clasico`/`centro`/
`dia` + ventana alta) en `front.py`, `hublayout.py`, `responsive_ui.vertical_hub`
y completó `agent_ui.py`. Dejó en `common` y `hub` un juego de claves que las
pantallas de la Ola 2 deben **referenciar** (no volver a crear — romperían la
paridad es/en):

**`lang/<code>/common.py`** (lo más reutilizable):
- `common.hint.*` — acciones de teclas: `section · pick · enter · terminal ·
  move · jump · quit · engine · info · menu · aim_open · key`.
- `common.status.*` — estado de agente: `active · in_use · ready · soon · idle ·
  working · running`.
- `common.git.*` — `clean · dirty_mark · clean_short · dirty_short · uptodate ·
  vs_origin`.
- `common.ago.*` — antigüedad relativa `sec/min/hour/day` (interpolan `{n}`).
- `common.cal.month_long.1..12 · month_short.1..12 · day_long.0..6 · dow.0..6` —
  meses y días; los usa el mini-calendario del `dia` y los debe reusar
  `calendario_tui` (Ola 2). `day_long` indexa por `weekday()` (0 = lunes).

**`lang/<code>/hub.py`** — títulos de sección (MAYÚSCULAS, para `full_box`/
`section_mark`; en `dia` pasan por `_dia_caps` que las `.upper()`a, así que el
mismo literal sirve): `hub.section.{gods,agents,menu,personalization,settings,
today,tone,branches,details,activity,monitor_live,lang,configs,calendar,upcoming}`
y con contador `hub.title.{agents_n,branches_n,tone_named}`. Más: `hub.cfg.* ·
hub.instr.* · hub.monitor.* · hub.hb.* · hub.det.* · hub.strip.* ·
hub.tono.group.* · hub.cal.* · hub.date.* · hub.sel.* · hub.ver.* · hub.franja.* ·
hub.hero.* · hub.classic.* · hub.narrow.* · hub.fullscreen_*`.

**Pendiente para la Ola 2 (dependencia del `tono`):** el mini-panel TONO del
`dia` (`hublayout._dia_tono_box`) traduce sólo los ENCABEZADOS de grupo
(`hub.tono.group.{manner,form,work}`). Los LABELS de dial (`amab/fran/…`) y sus
POLOS (`brutal/llano/serio/…`) salen de `personalidad.py` (datos del `tono`); los
traduce la Ola 2 junto con `tono_tui.py` + el catálogo `tono`. Hasta entonces, en
EN el mini-panel muestra los diales en español (es el único punto a medias, por
frontera de módulo — no por olvido).

## Distro

`i18n.py` y todo `lang/` (incluidos los sub-paquetes `lang/es/`, `lang/en/`)
**viajan al distro** (el cliente necesita EN): `make-dist.sh` es una denylist y
no los strippea. No muevas estos archivos a una carpeta que sí se strippee
(p. ej. `research/`, `tests/`, `runbooks/`).

## Pendientes conocidos (candidatos de fase 1)

- La **fila de etapas** del onboarding (`_fila_etapas`: `1 motores ── 2
  apariencia ── 3 agente`) sigue en español aunque la caja ya esté traducida —
  es un elemento compartido por las vistas `motores/apariencia/agente`, aún sin
  traducir; se traduce junto con ellas para no quedar a medias.
- Pantallas del cliente aún hardcodeadas: `motores`, `apariencia`, `agente`,
  `resumen` del onboarding; `calendario_tui`, `tono_tui`, `keybinds_tui`,
  `github_tui`, `actualizaciones_tui`, `add_agent_tui`. El «chrome» compartido
  del hub (`front.py` recinto/banner/hero/narrow, `hublayout` layouts
  `dia`/`centro`, `responsive_ui.vertical_hub`) quedó HECHO en la Ola 1.
