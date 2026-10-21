# El hub y sus teclas

El **hub** es lo que ves al escribir `workspace`: una caja con tus agentes y, debajo, el
**Mapa de la memoria** y tres entradas — **Menú**, **Personalización** e **Idioma**. Enter entra; el título de la caja dice
dónde estás (WORKSPACE › MENÚ) y Esc regresa. La caja tiene siempre el mismo tamaño: puedes
achicar la ventana hasta que solo quepa ella.

**Escribe para buscar.** Cualquier letra escribe en la búsqueda de arriba y la lista se filtra al
instante, sin importar mayúsculas ni acentos. Desde el inicio la búsqueda encuentra también lo de
dentro (por ejemplo «tema» → Personalización › tema).

<!-- Teclas verificadas contra front.py (_jump_map, lz_key, Tab, flechas).
La prueba tests/test_manual_compat.py falla si cambian. -->

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

## Sobre el agente apuntado

**← →** cambian su motor (`‹ motor ›`, se guarda en esta máquina; el próximo Enter ya lo usa) y
**Tab** muestra en una línea su motor, dónde vive su cerebro y qué está haciendo.

## Mapa de la memoria

La fila **Mapa de la memoria ›**, justo debajo de tus agentes, abre el mapa de cómo recuerda el
agente que tenías apuntado: el árbol real de su cerebro y, paso a paso, qué archivos lee y cuáles
escribe, en orden y en colores. ← → o las cifras `0` … `7` cambian de paso, ↑ ↓ desplaza si no
cabe, Tab cambia de agente, Enter abre lo que lo demuestra y Esc te regresa al hub. Es el mismo
mapa del primer renglón de Documentación.

## Menú

Las secciones del **Menú**. Se abren desde Menú › o buscándolas:

| Sección | Para qué |
|---|---|
| Agentes | tus agentes y sus opciones (Enter sobre uno); «+ agregar agente», al final de la lista, crea o carga uno nuevo |
| Actualizaciones | revisar, reparar y actualizar Workspace |
| Comandos | todo lo que puedes escribir en la terminal |
| Calendario | tu agenda, editable a pantalla completa |
| Tono | los diales de personalidad de tus agentes |
| Motores | estado de cada motor, qué puede hacer y sus conexiones |
| Usuarios | quién usa cada agente: «soy yo en esta PC», cambiar nombre, unir dos usuarios que son la misma persona (p. ej. el de la Mac y el de Windows) y crear uno nuevo. Cada usuario tiene una cédula (un ID fijo), así que renombrar nunca confunde a otra máquina; nada se borra |
| Documentación | todo lo que hace Workspace, en 13 capítulos (abrir una pestaña, cerrar, qué viaja, qué sale a la red, qué no hace…): cada uno con un mapa, el dato real de esta PC para el agente elegido, el archivo o comando que lo comprueba (Enter lo abre) y el ajuste que lo apaga |

## Las cifras

Las cifras `1` … `9` siguen el orden de tus agentes en el hub: el primero es `1`, el segundo `2`,
y así. Del décimo en adelante, usa las flechas o la búsqueda. Las letras escriben en la búsqueda
y `q` sale a tu terminal.
