# El hub y sus teclas

El **hub** es lo que ves al escribir `workspace`. Abre en **Inicio**: arriba, **Buscar**,
**Navegador**, **Guía** y ✕; en medio, la tarjeta del agente elegido (su monito, su nombre y su
motor) con **Conversar** y **Sesiones**; abajo, una fila con las secciones. La primera vez que lo
abres sale una guía corta; la vuelves a ver con `?` o con **Guía**.

Si todavía no tienes agentes, el hub abre con la tarjeta para agregar el primero.

<!-- Secciones y teclas verificadas contra hub_inicio.py (SECCIONES, SUBS) y
hub_secciones_r2.py (TECLAS). La prueba tests/test_manual_compat.py falla si cambian. -->

## Agregar un agente

**+ Agregar** abre la tarjeta para agregar un agente: uno nuevo, o uno que ya tienes («Ya tengo
un agente»). Está en Inicio, al pie de la lista de agentes, y en **Agentes**.
`workspace onboarding` abre el hub con esa tarjeta.

## Secciones

Desde Inicio, Tab llega a la fila de secciones; ← → cambia de sección, ↓ muestra sus partes y
Enter la abre. También las encuentras escribiendo su nombre.

| Sección | Qué hay |
|---|---|
| Agentes | Apariencia (la cara y el color de cada agente), Tono, Quién lo usa, Tablero y **+ Agregar** |
| Motores | cada motor de agentes y si está listo. «Iniciar sesión», «Instalar» y «Reparar» abren el programa oficial de ese motor en la terminal; al terminar vuelves a Motores |
| Skills | las skills de tus agentes |
| Calendario | tu agenda: agregas, cambias, marcas o quitas eventos |
| Ajustes | General (el idioma, entre otros), Apariencia (tema y fondo), Permisos, Usuarios, Uso, Actualizaciones (revisar, reparar o actualizar Workspace, con los pasos en vivo) y Conexiones (lo que Workspace conecta en cada motor) |
| Ayuda | Teclas, Comandos (lo que escribes en la terminal), Documentación (este manual) y Novedades |

Desde la terminal llegas directo: `workspace agentes` abre Agentes; `workspace tono`, Agentes ›
Tono; `workspace calendario`, Calendario; `workspace conexiones`, Ajustes › Conexiones; y
`workspace comandos`, Ayuda › Comandos. Con argumentos, esos comandos siguen en texto
([Comandos](comandos.md)).

## Teclas

La lista completa, según dónde estás, está en **Ayuda › Teclas** (o F1). Las de siempre:

| Tecla | Qué hace |
|---|---|
| Tab | otra área (Shift-Tab: la de antes) |
| ↑ ↓ ← → | moverte dentro del área |
| Enter | hacer lo enfocado |
| Esc | regresar un nivel |
| `q` | salir (fuera de la caja de escribir) |

En Inicio, ← → traen al agente de al lado y ↑ ↓ cambian su motor (se guarda solo). Enter
conversa, o hace lo que necesite su motor (por ejemplo, iniciar sesión). La tecla `s` abre sus
sesiones de su programa oficial y la `n`, la versión del navegador. Las demás letras buscan un
agente o una sección; `/` busca aunque escribas `s`, `n` o `q`.

## Las cifras

Las cifras `1` … `9` llevan directo a ese agente, en el orden de tus agentes: el primero es `1`,
el segundo `2`, y así. Del décimo en adelante, usa las flechas o la búsqueda. `q` sale a tu
terminal.

## Workspace en el navegador

**Navegador ↗** (arriba en Inicio, o la tecla `n`) abre tu navegador en la página local de
Workspace, solo en esta computadora, y el hub se queda donde estaba. Hay una sola página por
computadora: si ya está abierta (desde otro hub o con `workspace web`), se vuelve a abrir esa. Se
cierra con «Apagar» en la página, y se apaga sola si pasa un día sin que nadie la use. Para que se
abra sola cada vez que abres Workspace en una terminal, enciende **Abrir Workspace en el
navegador al iniciar** en Ajustes › General: solo lo hace si no tienes otro hub abierto en esta
computadora.

La página está en español. Si tu idioma es otro, te lo dice en una línea.

## Revisión de skills visible

Viene apagada. En los ajustes de revisión de skills puedes elegir cuándo revisa el agente: al abrir la siguiente sesión, al cerrar o con botón. También eliges el motor: el de la sesión o uno fijo instalado. El booleano antiguo encendido conserva «al abrir» mientras no elijas otro modo. Hermes y OpenClaw solo usan el botón.

Antes de empezar ves una estimación de tokens; es aproximada, no una factura ni un tope de consumo del motor. Cada tanda tiene como máximo tres revisiones. Las sesiones pendientes de una misma pestaña se leen juntas; lo de más de siete días vence.

Con herdr se abre una pestaña sin quitarte el foco: el chat real a la izquierda y los pasos a la derecha. **Parar** deja pendiente lo que falta. El reporte del agente no cuenta como comprobación: el cierre debe comprobar la escritura en la sesión receptora. La pestaña cierra al acabar. Deshacer solo restaura archivos cuya escritura aparece en esa sesión y se niega si ya cambiaron después; los archivos nuevos se archivan. Si el motor no registra autoría suficiente, no se ofrece deshacer esos archivos.

Sin herdr, las revisiones usan la misma ventana, una tras otra. Ves el costo antes y puedes dejarlas para después. Ctrl+C para la tanda. También puedes usar `workspace revision ahora`; `workspace revision ver <tanda> [índice]` muestra el cambio y `workspace revision deshacer <tanda> [índice]` lo restaura (el índice empieza en 0).

La función debe seguir apagada para clientes hasta completar la prueba en vivo de los nueve motores.

Deshacer exige además reconstruir el contenido posterior a la escritura de la receptora; si no hay evidencia suficiente, no restaura y explica el motivo.
