# Novedades de Workspace

Qué cambia en cada versión, contado desde tu lado de la pantalla. La versión
que tienes la ves con `workspace version` (y abajo a la derecha en el hub).
English: [CHANGELOG.en.md](CHANGELOG.en.md).

Cómo leer esto: cada versión tiene su número (`MAYOR.MENOR.PARCHE`). Un
cambio de PARCHE arregla cosas; uno de MENOR trae funciones nuevas sin romper
nada; uno de MAYOR avisa con tiempo si algo cambia de forma.

## 0.3.3 — 2026-10-14

**Arreglos**
- El hub ya no muestra el aviso de «configuración a medias». Se basaba en cómo
  saliste del primer arranque y no se actualizaba, así que podía seguir ahí
  aunque ya lo hubieras terminado. Para repasar el primer arranque:
  `workspace onboarding`.

## 0.3.2 — 2026-10-14

**Arreglos**
- Si ya tenías motores y agentes y solo te asomaste al primer arranque, el hub
  ya no te muestra para siempre el aviso de «configuración sin terminar».

## 0.3.1 — 2026-10-14

**El hub, más simple: cada sección en una cajita**
- Cada sección muestra solo lo que necesitas para usarla, en una caja
  centrada. La explicación (cómo funciona, con sus mapas) está detrás de la
  tecla `i`.
- **Agentes:** tus agentes arriba y, debajo, las opciones del elegido (Enter
  o →; ← o Esc regresan). Agregar un agente vive aquí mismo: el renglón
  «+ agregar agente» al final de la lista (o la tecla `a`); si aún no tienes
  agentes, se abre directo el formulario.
- **Crear un agente:** los campos se ven vacíos (antes traían un «ej. …»
  adentro que parecía ya lleno). El ejemplo y la explicación del campo en el
  que estás van debajo del formulario, y si escribes mucho, ahí ves tu texto
  completo. En **tus preferencias** cada renglón dice qué es: interruptores
  sí/no, lo que elegiste con «›» para cambiarlo, y debajo una frase sobre el
  renglón elegido; su `i` resume lo que vas a crear, tu consumo y cómo nace.
- **Motores:** la lista a la izquierda y las opciones a la derecha. Al abrir
  se verifica de verdad si tienes sesión en cada uno: listo · sin sesión · no
  instalado.
- **Actualizaciones:** tu versión, si hay una nueva y solo lo que puedes hacer
  en ese momento: actualizar (cuando hay versión nueva), revisar y reparar,
  solo revisar, volver a la versión anterior (cuando hay a cuál) y si se
  actualiza sola (sí · solo avisar · no).
- **Comandos:** la lista por grupos y, debajo, cómo se escribe el elegido y
  qué hace. Con `i` se abre a la derecha su mapa y cuándo te sirve, y cambia
  conforme te mueves.
- **El primer arranque** usa la misma cajita: cada paso en una caja con el
  avance arriba (motores → apariencia → agente), solo lo que hay que decidir
  y la acción principal abajo; lo que explica cada paso está en `i`. Elegir
  una opción ya no te hace avanzar: en cada paso (también en Tono) avanzas
  con el botón «✦ continuar», y al final «✦ ir al hub» abre el hub (antes te
  dejaba en la terminal).
- **Calendario** se queda igual y gana su explicación en `i`. **Tono** es la
  cajita con tus agentes y sus diales.

**Fuera lo que no se usaba**
- **Atajos** salió del menú: las teclas `1` a `9` siempre siguen el orden de
  tus agentes en el hub.
- **Google Calendar** queda en pausa mientras lo mejoramos: no aparece en el
  calendario ni en el primer arranque.

**Arreglos**
- Motores ya no se queda sin teclado mientras verifica las sesiones.
- Los títulos de las secciones ya no llevan una sombra debajo, igual que el
  del hub.

## 0.3.0 — 2026-10-13

**Tú decides cuánto puede hacer cada agente sin preguntarte**
- Al crear o cargar un agente eliges dos cosas: si lee y escribe en su
  cerebro sin preguntarte (**sí** de entrada: es su trabajo principal) y si
  quieres la revisión automática de skills al cerrar cada sesión (**no** de
  entrada). Si no hay terminal interactiva (un script), se usan esos valores;
  `agent_admin.py` acepta `--autonomy brain|ask` y `--skill-review`.
- Las dos se cambian después en **Agentes** (elige el agente y Enter),
  agente por agente. Si apagas el acceso a su cerebro, te pregunta antes de
  crear o editar cualquier archivo, también dentro de él. Sin abrir el hub:
  `agent_admin.py prefs <agente> --autonomy brain|ask
  --skill-review|--no-skill-review`.
- Tu respuesta queda guardada con el agente (en su `agent.json`, viaja con el
  cerebro) y cada motor la aplica a su manera.
- Con Claude Code, un agente nuevo lee, crea y edita archivos **dentro de su
  cerebro** sin pedirte permiso; para la terminal, los archivos de fuera y la
  red te pregunta. Nunca se desactivan las protecciones del motor.
- Antes, el instalador dejaba a todo agente de Claude Code correr cualquier
  comando sin preguntar (e incluía una integración de tienda que no era
  tuya). Al actualizar, tus agentes pasan solos a lo nuevo: libres solo
  dentro de su cerebro (su configuración anterior queda respaldada). Correr
  comandos sin preguntar ya no es una opción.
- «Auto-aceptar ediciones» en cada sesión de Claude Code (`agentes.auto_mode`)
  viene ahora **apagado**: mandan los permisos del cerebro. Si lo quieres de
  vuelta: `python3 settings.py set agentes.auto_mode on` en la carpeta de
  Workspace.

**La revisión de skills es opcional y funciona con los tres motores**
- Viene **apagada**. Si la prendes para un agente, al cerrar cada sesión su
  propio motor (Claude Code, Codex o Antigravity) revisa en segundo plano lo
  que corregiste y mejora sus skills; las skills nuevas quedan como propuesta
  hasta que tú las apruebes.
- Lee una copia neutral de la sesión (no el archivo interno del proveedor), no
  usa la terminal ni la red, nunca hace esperar el cierre y usa un poco de tu
  suscripción.
- Revisa el cerebro correcto aunque la sesión termine dentro de una subcarpeta
  (antes revisaba esa subcarpeta e ignoraba lo que elegiste para el agente);
  con Claude Code ya no queda guardada como una conversación más del agente, y
  su reporte llega al registro de revisiones aunque Claude Code no lo deje
  escribir ahí. Se prende o apaga en **Agentes** (elige el agente y Enter); a los agentes que no
  eligieron les aplica el ajuste global `hooks.skill_review` (`python3 settings.py set hooks.skill_review on`
  en la carpeta de Workspace).

**El doctor ahora solo revisa y repara lo esencial**
- `workspace doctor` (y lo que ves al final de `workspace update`) revisa solo
  lo esencial: tus agentes, sus hooks y comandos, git/Python/el motor que usas
  y las actualizaciones. Si algo de eso no funciona, te lo dice y lo arregla.
- Se acabaron los avisos que no tenían que ver contigo: convenciones internas
  de cerebros (BOOT, INDEX, manifiestos, banner), GitHub CLI, canal del equipo,
  modo autónomo y funciones opcionales que no usas (voz, terminal partida).
- No tener agentes todavía es normal: ya no sale como aviso.
- Ahora detecta y arregla los hooks de un agente que apuntan a una carpeta de
  Workspace que ya no existe (por ejemplo, tras mover o reinstalar).
- La voz se prepara cuando tú quieras con `workspace voice --setup`; el doctor
  ya no la revisa.

**Fuera lo que ya no usabas**
- Las teclas de letra que ya no abrían nada (c, o, k, u, g, s, b, v, m, i, l)
  salieron de Atajos, del resumen del primer arranque y del manual: en el hub
  las letras buscan; las teclas rápidas son `1`–`9` (tus agentes) y `q`.
  Atajos ahora solo cambia la cifra de cada agente.
- Se retiró `workspace versiones` (y `ramas`/`branches`): era un mapa de
  ramas de git para quien desarrolla Workspace, no para ti.
- Se retiró la vieja pantalla de configuración, que ya no se podía abrir
  desde el hub. Tus ajustes siguen: el tema y el fondo en Personalización,
  los permisos y la revisión de skills en Agentes (Enter sobre el agente), y
  cualquier ajuste con `python3 settings.py set <ajuste> <valor>`.
- Los agentes nuevos ya no reciben una galería de emblemas que nada
  mostraba.
- Se retiró `workspace foco` (`focus`): guardaba un foco del día que ninguna
  pantalla mostraba. Tu agenda y el calendario siguen igual.

**Arreglos**
- Crear un agente ya no termina con «⚠ verificación final 1 placeholder(s)
  sin llenar»: la ficha de dueño del agente nuevo (BOOT/02-TEAM.md) ya se
  llena.
- Si venías de la instalación anterior, se había colado en tu lista un agente
  interno que nunca fue tuyo; el doctor lo revisaba y no dejaba retirar los
  restos de esa instalación. Un ajuste automático lo quita (con respaldo) y
  esos restos ya se pueden retirar con `workspace migrar-legado`.
- «Reanudar sesión» ya no da un falso aviso cuando otra carpeta se llama igual
  que tu cerebro, y solo se revisa en agentes de Claude Code.

**Instalación y privacidad**
- El instalador ya no pregunta «¿Quién eres?».
- Pide el CLI del motor que vayas a usar (Claude Code, Codex o Antigravity),
  no siempre Claude Code.
- Tus sesiones se conservan **un año** (antes, diez). Si ya tenías el valor que
  ponía nuestro instalador, baja a 365 días; si tú elegiste otro, no se toca.
- Los cerebros nuevos ya no traen carpetas de sesión con nombres de otras
  personas.

## 0.2.0 — 2026-10-13

**Un hub nuevo: el Lanzador**
- El hub es ahora una sola caja con tus agentes y, debajo, Menú,
  Personalización e Idioma. Enter entra, Esc regresa y el título te dice
  dónde estás.
- Escribe para buscar: la lista se filtra al instante y encuentra también lo
  de dentro (por ejemplo «tema»).
- ← → cambian el motor del agente apuntado (`‹ motor ›`); Tab muestra su
  información.
- La caja tiene siempre el mismo tamaño: la ventana se puede achicar hasta
  que solo quepa ella. El hub anterior y sus variantes ya no existen.
- Esc te regresa al hub desde cualquier sección (Calendario, Tono y
  Actualizaciones antes te sacaban a la terminal) y desde el menú de
  sesiones de un agente, que ahora muestra solo su nombre y sus sesiones.

**Actualizaciones con red de seguridad, y opcionales**
- Tú eliges si Workspace se actualiza solo: **automático** (como hasta ahora),
  **solo avisar** (te dice que hay versión nueva y tú decides) o **apagado**.
  Se cambia en Actualizaciones (tecla `a`) o con `workspace update --auto`.
- Antes de usar una versión nueva, Workspace comprueba que arranca en tu
  computadora. Si no arranca, vuelve solo a la que tenías y espera a que
  publiquemos un arreglo. No tienes que hacer nada.
- Si una versión nueva no te convence, `workspace update --rollback` te
  devuelve a la anterior. Tus agentes, cerebros y ajustes no se tocan.
- Los ajustes que una versión necesita hacer en tu máquina se aplican a la
  vista y quedan anotados. Si uno falla, Workspace sigue funcionando y
  `workspace doctor` te dice qué pasó y cómo seguir.
- `workspace version` muestra tu versión, tu última actualización y estas
  novedades. La versión también aparece abajo a la derecha del hub.

**Ayuda y diagnóstico**
- `workspace doctor --bundle` arma un ZIP de diagnóstico para pedir ayuda,
  con tus datos personales tachados y un LEEME que dice qué contiene.
- Nuevo manual de uso en `manual/` (español e inglés), con una tabla honesta
  de qué funciona con cada motor en cada sistema y qué datos salen de tu
  computadora.
- Plantilla para reportar problemas y canal privado para reportar fallos de
  seguridad (`SECURITY.md`).

**Comandos**
- Cada comando acepta su nombre en español y en inglés (`tono`/`tone`,
  `actualizar`/`update`…); todos los nombres de antes siguen funcionando.
- La pantalla Comandos busca con `/` y ejecuta el comando con Enter (pide
  confirmación en los delicados).
- `workspace comandos --json` le da la lista completa a tus agentes.

**Instalar, empezar y desinstalar**
- El instalador revisa tu computadora antes de tocar nada (Python, git,
  espacio, carpetas en la nube) y te dice qué arreglar, sin culparte.
- Al terminar la bienvenida ves las teclas que importan (las tuyas, si las
  cambiaste).
- Desinstalar muestra qué se borra y qué se conserva, ofrece un respaldo de
  tus ajustes (sin tus claves) y se niega a borrar carpetas que no son de
  Workspace.

**Seguridad**
- Se cerraron los fallos pendientes de una auditoría interna: la bóveda de
  claves ya no deja un archivo legible al guardar, el bus no despacha dos veces
  el mismo mensaje, la revisión de cambios de un agente detecta más tipos de
  llaves y comandos peligrosos, y una clave nunca se guarda a nombre de otra
  cuenta.

**Tono de los agentes**
- Los diales de tono son más firmes: Longitud da un tope concreto de palabras, manda sobre la forma de responder y gana si choca con otro dial. En Codex y Antigravity el tono va primero en las instrucciones de arranque.

**Temas**
- Un tema define una sola paleta y de ella salen los colores del hub, de la
  terminal y del tema dentro de Claude Code. Lo que hayas hecho a mano no se
  pisa. Nada cambia en pantalla si no eliges un tema nuevo.
- Tema nuevo **Blanco**: fondo blanco y todo lo demás en negro, el inverso
  de Mono. Los dos usan solo dos colores puros, sin grises.
- El tema y el fondo que eliges en el hub pintan también las sesiones de
  tus agentes: la barra de estado, el banner y el tema dentro de Claude
  Code. Si editaste a mano el tema de Claude Code, se respeta.

**Limpieza**
- El nombre anterior del producto desaparece de pantallas y textos; Workspace
  sigue reconociendo y migrando restos de la instalación anterior.
- La sección GitHub del hub se retira por ahora mientras la rehacemos.

## 0.1.0 — 2026-06-18

- Primera versión: hub en la terminal, agentes con su propio cerebro, motores
  intercambiables, onboarding guiado, doctor que revisa y repara, y
  actualizaciones automáticas.
