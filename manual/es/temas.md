# Temas y apariencia

Workspace trae ocho temas de color para el hub (**bruma**, el de fábrica, más rose,
durazno, lavanda, salvia, cyberpunk, mono y blanco) y te deja elegir el fondo por separado.
**Blanco** es el único claro: fondo blanco y todo en negro. Por eso ignora los fondos
oscuros que elijas aparte (dejarían el texto invisible).

## Cambiar el tema

- En el **primer arranque**, paso *Apariencia* (lo repites con `workspace onboarding`).
- En cualquier momento, en el hub: entra a **Personalización ›** (o escribe «tema»), elige
  la fila **tema** o **fondo** y pulsa Enter para pasar al siguiente. El cambio se guarda al
  momento.

<!-- Verificado contra front.py (cycle_pin), settings.py (ui.theme default «bruma»,
ui.background, ui.background_custom, ui.hub_pins) y onboarding_tui.py (paso apariencia). -->

El **fondo** se puede cambiar sin cambiar el tema: negro, grafito, azul, verde o violeta;
**tema** vuelve al fondo del tema activo, y **personalizado** usa tu propio color. Ese color se
define una vez, desde la carpeta de Workspace (en Windows, `python` en vez de `python3`):

```bash
python3 settings.py set ui.background_custom "#1a1b26"
```

Personalización tiene también **brillo** (más vivo o más apagado), **luz roja** (modo noche)
y **auto-abrir** (que el hub aparezca al abrir la terminal).

## Qué cambia y qué no

- El tema pinta **el hub y las pantallas de Workspace**.
- Cada agente puede tener sus propios colores de terminal; al salir del agente se restauran
  los tuyos.
- Con Claude Code, el agente también puede traer su tema dentro de Claude Code. Con otros
  motores solo se aplican los colores de terminal.
- Tus elecciones se guardan **en esta máquina** y sobreviven a las actualizaciones.

¿Algo se ve descuadrado? Agranda la ventana; en Windows usa **Windows Terminal**.
