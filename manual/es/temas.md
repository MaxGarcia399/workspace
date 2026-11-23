# Temas y apariencia

Workspace trae ocho temas de color para el hub (**bruma**, el de fábrica, más rose,
durazno, lavanda, salvia, cyberpunk, mono y blanco) y te deja elegir el fondo por separado.
**Blanco** es el único claro: fondo blanco y todo en negro. Por eso ignora los fondos
oscuros que elijas aparte (dejarían el texto invisible).

## Cambiar el tema

- El primer arranque ya no lo pregunta: empiezas con el tema de fábrica.
- En cualquier momento, en el hub: **Ajustes › Apariencia**, filas **Tema del hub** y **Fondo
  independiente**.

<!-- Verificado contra hub_secciones_r2.py (ajustes_filas: grupos General y Apariencia) y
settings.py (ui.theme default «bruma», ui.background, ui.background_custom, pin_label). -->

El **fondo** se puede cambiar sin cambiar el tema: negro, grafito, azul, verde o violeta;
**tema** vuelve al fondo del tema activo, y **personalizado** usa tu propio color. Ese color se
define una vez, desde la carpeta de Workspace (en Windows, `python` en vez de `python3`):

```bash
python3 settings.py set ui.background_custom "#1a1b26"
```

Ajustes › Apariencia tiene también **Brillo** (más vivo o más apagado) y **Luz roja (modo
noche)**. En Ajustes › General están **Abrir al abrir la terminal** (que el hub aparezca al
abrir la terminal) y **Abrir Workspace en el navegador al iniciar** (que la página se abra junto
con el hub, si no hay otro hub abierto).

## Qué cambia y qué no

- El tema pinta **el hub y las pantallas de Workspace**.
- Cada agente puede tener sus propios colores de terminal; al salir del agente se restauran
  los tuyos.
- Con Claude Code, el agente también puede traer su tema dentro de Claude Code. Con otros
  motores solo se aplican los colores de terminal.
- Tus elecciones se guardan **en esta máquina** y sobreviven a las actualizaciones.

¿Algo se ve descuadrado? Agranda la ventana; en Windows usa **Windows Terminal**.
