# El hub y sus teclas

El **hub** es lo que ves al escribir `workspace`: una caja con tus agentes y, debajo, tres
entradas — **Menú**, **Personalización** e **Idioma**. Enter entra; el título de la caja dice
dónde estás (WORKSPACE › MENÚ) y Esc regresa. La caja tiene siempre el mismo tamaño: puedes
achicar la ventana hasta que solo quepa ella.

**Escribe para buscar.** Cualquier letra escribe en la búsqueda de arriba y la lista se filtra al
instante, sin importar mayúsculas ni acentos. Desde el inicio la búsqueda encuentra también lo de
dentro (por ejemplo «tema» → Personalización › tema).

<!-- Teclas de fábrica verificadas contra keybinds.py (_AGENTES, _ACCIONES, _MENU_BASE,
RESERVADAS, auto-derivación de Motores) y front.py (lz_key, Tab, flechas). La prueba
tests/test_manual_compat.py falla si cambian. -->

## Moverse y entrar

| Tecla | Qué hace |
|---|---|
| ↑ ↓ | moverte por la lista |
| Enter | abrir lo seleccionado: un agente se lanza; una entrada con `›` se abre; en Personalización cambia el valor |
| Esc | borrar la búsqueda o regresar un nivel |
| letras | buscar |
| ⌫ | borrar la última letra de la búsqueda |
| `1` … `9` | con la búsqueda vacía: apuntar al agente con ese número; la misma tecla otra vez lo abre |
| `q` | con la búsqueda vacía: salir a tu terminal normal |

Con la ventana muy chica el hub pasa a una vista compacta de texto con las mismas acciones; ahí
también funcionan las teclas de las tablas de abajo.

## Sobre el agente apuntado

En el hub: **← →** cambian su motor (`‹ motor ›`, se guarda en esta máquina) y **Tab** muestra en
una línea su motor, dónde vive su cerebro y qué está haciendo. En la vista compacta:

| Tecla | Qué hace |
|---|---|
| `m` | cambiar su **motor** (se guarda en esta máquina; el próximo Enter ya lo usa) |
| `i` | ver en una línea su motor, dónde vive su cerebro y qué está haciendo |

## Menú

Las secciones del **Menú**. En el hub se abren desde Menú › (o buscándolas); en la vista compacta,
con su tecla:

| Tecla | Sección | Para qué |
|---|---|---|
| `g` | Agregar agente | crear un agente nuevo o cargar uno que ya tengas |
| `b` | Agentes | ver la configuración y el cerebro de cada agente |
| `u` | Actualizaciones | revisar, reparar y actualizar Workspace |
| `v` | Comandos | todo lo que puedes escribir en la terminal |
| `k` | Atajos | **cambiar cualquiera de estas teclas** |
| `c` | Calendario | tu agenda, editable a pantalla completa |
| `o` | Tono | los diales de personalidad de tus agentes |
| `s` | Motores | estado de cada motor, qué puede hacer y sus conexiones |

Cada tecla aparece junto a su sección en el propio menú. Si en el futuro llega una sección
nueva, recibe una tecla libre automáticamente; la ves en el menú y en **Atajos**.

## Cambiar las teclas

**Atajos** (`k`) muestra todas las teclas y te deja cambiarlas. Solo se guardan tus cambios,
en esta máquina; si algo sale mal, vuelven las de fábrica. Una tecla pertenece a una sola
acción: si ya está ocupada, Atajos te dice quién la usa. No se pueden asignar `q`, `l`,
espacio, Enter, Esc, Tab ni las flechas, ni las letras `t` `a` `e` `x` `f` `d` `n` `p`, que
usan otras pantallas.
