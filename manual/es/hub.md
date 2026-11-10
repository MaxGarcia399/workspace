# El hub y sus teclas

El **hub** es lo que ves al escribir `workspace`: una caja con tus agentes y, debajo, tres
entradas — **Menú**, **Personalización** e **Idioma**. Enter entra; el título de la caja dice
dónde estás (WORKSPACE › MENÚ) y Esc regresa. La caja tiene siempre el mismo tamaño: puedes
achicar la ventana hasta que solo quepa ella.

Debajo de tus agentes va **◆ Decisores**, con el modelo de decisión activo donde un agente lleva
su motor («Jev»). Sin modelo dice «configurar» (sus primeros 7 días en esta máquina, «nuevo») y
Enter te lleva a Motores → Modelos de decisión para conectar uno; con modelo, Enter abre Decisores.
También se abre con el `0`.

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
| `0` | con la búsqueda vacía: abrir Decisores (o Motores → Modelos de decisión si aún no tienes modelo) |
| `q` | con la búsqueda vacía: salir a tu terminal normal |

## Sobre el agente apuntado

**← →** cambian su motor (`‹ motor ›`, se guarda en esta máquina; el próximo Enter ya lo usa) y
**Tab** muestra en una línea su motor, dónde vive su cerebro y qué está haciendo. En la fila de
**◆ Decisores**, **← →** cambian el modelo de decisión activo entre los que están listos y
«apagado» (`‹ Jev ›`, se guarda como en Decisores → Ajustes).

## Menú

Las secciones del **Menú**. Se abren desde Menú › o buscándolas:

| Sección | Para qué |
|---|---|
| Agentes | tus agentes y sus opciones (Enter sobre uno); «+ agregar agente», al final de la lista, crea o carga uno nuevo |
| Actualizaciones | revisar, reparar y actualizar Workspace |
| Comandos | todo lo que puedes escribir en la terminal |
| Calendario | tu agenda, editable a pantalla completa |
| Tono | los diales de personalidad de tus agentes |
| Motores | dos cuadritos: **Motores de agentes** (estado de cada motor, qué puede hacer y sus conexiones) y **Modelos de decisión**, con el mismo diseño: la lista de modelos (Jev, OpenRouter y Liquid en la nube; Ollama en esta computadora) con su estado real y, al lado, sus opciones — conectar tu llave (en la nube es lo único que hay que configurar; se queda en esta PC), elegir el modelo si trae varios, probarlo con una llamada real (cuánto tarda, cuántos tokens usa y cuánto costó) y ver su límite de contexto y su precio aproximado. Ollama no lleva llave ni costo y tu contexto no sale de esta computadora; si le falta algo, dice el siguiente paso en una línea (abrirlo, actualizarlo a 0.35.0 o `ollama pull nimble`) |
| Conversaciones | lo que tus agentes se dicen entre sí: salas de hasta 6 agentes, cada uno en su pestaña y de cualquier motor (Activas, Todas, Archivadas). Cabecera como WhatsApp (tema, objetivo e integrantes; `i` o clic en el tema = info del grupo) y cada mensaje con el color de quien habla. **e** escribe como tú (al último que habló, o a quien nombres con «@nombre»), **p** pausa o reanuda, **c** cierra (dos veces), **r** archiva y **b** borra una archivada; **t** cambia la espera por respuesta (15 min a 24 h); si un pedido vence, **m** le da 30 min más y **x** lo cancela; **a** abre la pestaña de quien falta. En una ventana chica se ve como el celular: la lista o el chat. Se actualiza sola; lo que leíste se guarda solo en esta PC. Con Decisores › Conversaciones encendido, un decisor puede callar un pedido que solo agradece, pausar una sala que da vueltas y sugerir cerrarla (todo marcado con ◆); apagado, todo igual |
| Usuarios | quién usa cada agente: «soy yo en esta PC», cambiar nombre, unir dos usuarios que son la misma persona (p. ej. el de la Mac y el de Windows) y crear uno nuevo. Cada usuario tiene una cédula (un ID fijo), así que renombrar nunca confunde a otra máquina; nada se borra |
| Decisores | qué modelo de decisión elige entre opciones fijas (Jev, OpenRouter o Liquid en la nube, Ollama en esta computadora, o ninguno: de fábrica no hay uno activo) y en qué usos ayuda; los modelos se conectan y se prueban en Motores → Modelos de decisión, una sola vez (el primero que queda listo se activa solo). Usos: memoria, evals, skills, seguridad y conversaciones de Workspace, y elegir, revisar, mejor prompt y repartir para tus agentes; cada uso con su nivel (apagado · observa · sugiere · decide). Preguntar para probarlo a mano, con el contexto que elijas (nada, la pestaña, sesiones, la memoria o todo el cerebro —si no cabe, lo más relevante; si nada coincide, lo más reciente—; cada nivel dice antes cuántos tokens y cuánto cuesta, y `v` muestra qué fuentes van; si el modelo dice que no cupo, Workspace recorta y vuelve a intentar solo). Si algo falla, el aviso dice qué pasó y qué hacer, y `d` muestra el detalle técnico. Un `.md` con `privado: true` en su frontmatter, o dentro de una carpeta `privado/`, nunca se manda; tampoco lo que es de otras personas en un cerebro compartido (sus sesiones, perfiles, bandeja y memoria), los chats, los mensajes entre agentes, las bitácoras ni los archivos que empiezan con `_` dentro de `deliverables/`, y los secretos se quitan antes de salir. Historial para ver qué pasó, qué cambió cada decisión y cuántas hubo hoy, y calificar si acertó; junto al umbral de cada uso, sus últimas confianzas. Todo viene apagado: así no sale nada; cada uso que enciendas con un modelo en la nube manda su pregunta y un contexto mínimo. La bitácora se queda en esta PC |
| Documentación | el mapa de la memoria (su primer renglón) y todo lo que hace Workspace, en 13 capítulos (abrir una pestaña, cerrar, qué viaja, qué sale a la red, qué no hace…): cada uno con un mapa, el dato real de esta PC para el agente elegido, el archivo o comando que lo comprueba (Enter lo abre) y el ajuste que lo apaga |

## Mapa de la memoria

Está en **Documentación** (Menú › Documentación): su primer renglón, o la tecla `m` desde
cualquier capítulo, abre el mapa de cómo recuerda el agente elegido: el árbol real de su cerebro
y, paso a paso, qué archivos lee y cuáles escribe, en orden y en colores. ← → o las cifras
`0` … `7` cambian de paso, ↑ ↓ desplaza si no cabe, Tab cambia de agente, Enter abre lo que lo
demuestra y Esc te regresa a los capítulos.

## Las cifras

Las cifras `1` … `9` siguen el orden de tus agentes en el hub: el primero es `1`, el segundo `2`,
y así. Del décimo en adelante, usa las flechas o la búsqueda. El `0` abre Decisores. Las
letras escriben en la búsqueda y `q` sale a tu terminal.
