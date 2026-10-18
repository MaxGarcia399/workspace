# Novedades de Workspace

Qué cambia en cada versión, contado desde tu lado de la pantalla. La versión
que tienes la ves con `workspace version` (y abajo a la derecha en el hub).
English: [CHANGELOG.en.md](CHANGELOG.en.md).

Cómo leer esto: cada versión tiene su número (`MAYOR.MENOR.PARCHE`). Un
cambio de PARCHE arregla cosas; uno de MENOR trae funciones nuevas sin romper
nada; uno de MAYOR avisa con tiempo si algo cambia de forma.

## 0.4.1 — 2026-10-18

**Arreglos**
- La sección **Usuarios** ya no muestra tres nombres que no son de nadie. Los
  agentes creados con la 0.2.0 o antes traían tres carpetas de ejemplo vacías
  y la 0.4.0 las tomaba por usuarios. Al abrir el agente (o la sección),
  Workspace las quita solo: el perfil que les había creado queda en
  `STATE/users/_archivo/`, y no toca nada que tenga pestañas, preferencias o
  memoria, ni a quien usa esa máquina.

## 0.4.0 — 2026-10-18

**Novedades**
- **Cada pestaña recuerda lo mismo en cualquier motor.** Tu agente guarda lo importante en el momento, con una etiqueta (decisión, pendiente, hecho…), y al abrir la pestaña —en ese motor o en otro— recibe el resumen, lo que sigue abierto, lo nuevo y una «maleta» con lo último que pasó en el otro motor. Workspace lo ordena y archiva solo, sin IA y sin que tengas que hacer nada; nada se borra.
- Nueva sección **Usuarios** en el menú: quién usa cada agente, «soy yo en esta PC», cambiar nombre y unir dos usuarios que son la misma persona (por ejemplo, el de tu Mac y el de tu PC). Cada usuario tiene una cédula fija, así que otra máquina con un nombre viejo entra sola al correcto.
- Nueva sección **Documentación** en el menú: todo lo que hace Workspace, capítulo por capítulo, con un mapa simple, lo que está pasando ahora en tu PC y cómo comprobarlo tú (Enter abre el archivo).
- Ningún proceso con IA trabaja sin una ventana abierta: se retiró el «destilador» que resumía la memoria por su cuenta y te pedía aprobar propuestas. Si tienes encendida la revisión de skills, la hace tu agente al abrir su siguiente sesión, a la vista.
- **Tu agente mantiene solo sus skills, su memoria y su identidad.** No te pide aprobar skills ni confirmar lo que anota; una vez por semana cura su biblioteca de skills por su cuenta, y completa su personalidad (`BOOT/00-SOUL.md`) con lo que le dijiste al crearlo y con tus correcciones, nunca con lo que lee en documentos o páginas. Todo queda recuperable y te lo cuenta en la línea del final de su respuesta.
- Si el motor de un agente no está instalado, el agente ya no se bloquea: te ofrece abrirlo con otro motor, solo esta vez o para siempre.
- Cerrar la ventana con la X ya no pierde nada: la memoria de la pestaña se ordena al cerrar o, si no alcanzó, la próxima vez que abres ese agente.
- Con OpenClaw ya puedes tener varios agentes abiertos a la vez (antes, con uno abierto, los demás no abrían). La primera pestaña tarda unos segundos más en abrir y, al cerrar la última, OpenClaw se apaga solo.
- Claude Code guarda su memoria propia dentro del cerebro, en una carpeta por persona: viaja contigo a tus otras máquinas y, en un cerebro compartido, el Claude Code de cada quien carga solo la suya y no confunde de quién es (se apaga en Ajustes).
- Antigravity guarda la memoria sin pedirte permiso en cada nota.

**Lo que esta versión cambia en tus cerebros al actualizar**

Lo hace sola, una vez, en cada agente. Antes de mover o cambiar algo lo copia a un respaldo, y nada se borra.
- La identidad de tus agentes pasa a `BRAIN.md`, un archivo que no es de ningún proveedor. Nada cambia en cómo usas a tus agentes: cada motor sigue entrando por su archivo de siempre (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`), que ahora solo apunta a `BRAIN.md`. Si algún agente tenía algo poco común (por ejemplo, editaste su identidad hace un momento), se deja como estaba y `workspace doctor` te lo cuenta. Para volver atrás: `workspace migrate --undo 202610151600_brain_identity_neutral`.
- Las instrucciones de memoria de tus agentes se ponen al día, sin importar con qué versión los creaste; también si el agente llega después (instalación nueva u otra máquina), al cargarlo. Si escribiste tus propias reglas de memoria, no se tocan: el agente igual recibe al abrir cómo guardar.
- La bandeja donde el destilador dejaba propuestas para aprobar a mano (`STATE/DESTILADO.md`) pasa a `STATE/memoria-archivo/`. Las skills propuestas que esperaban tu aprobación pasan a `skills/_archive/` si la revisión de skills de ese agente está apagada; si está encendida, se quedan hasta su siguiente revisión, donde tu agente integra las que sirven y las marca resueltas por su cuenta, y Workspace las archiva solo.
- Nada en tus cerebros espera tu aprobación. Las instrucciones de skills, memoria e identidad que pedían a una persona (aprobar skills nuevas, skills «intocables», confirmar antes de anotar en la memoria, diseñar a mano la personalidad del agente) se ponen al día, igual que los pasos que hacían que el motor te pidiera permiso (registrar el uso de una skill con un comando, un `git commit` antes de curar). Solo cambian las líneas que siguen tal como las dejó Workspace: lo que escribiste tú no se toca y tu agente recibe al abrir que esas aprobaciones se retiraron. Lo que quedaba en `skills/_propuestas/` (su README y `_mejoras/`) pasa a `skills/_archive/`.
- El `.gitignore` de cada cerebro suma las carpetas de trabajo de Workspace (`.claude/locks/`, `.claude/memoria-entrada/` y `.claude/skill-review/`), también en los cerebros que ya tenías.
- Si un cerebro no se puede actualizar (por ejemplo, un archivo bloqueado por la sincronización), los demás se actualizan igual y ese se reintenta solo la próxima vez.
- Si compartes un cerebro entre máquinas (por ejemplo, tu Mac y tu PC con Obsidian), cada una puede actualizar su copia antes de recibir la de la otra sin que al sincronizarse quede repetido lo archivado: el nombre sale del contenido (`DESTILADO-<huella>.md`, `propuestas-<huella>/`), no del día, y lo que otra máquina ya archivó no se archiva otra vez.

**Privacidad y seguridad**
- Las fichas de tus cuentas (por ejemplo, Google Calendar) y las llaves que guardaste en Workspace ya no llegan a los motores ni a lo que ejecutan tus agentes; solo las usa el hub.
- Una conexión que lleva una llave nunca la manda a otro servidor, y el correo comprueba que habla con el servidor correcto.
- `GEMINI.md` queda limpio al cerrar (sin la ruta de tu PC ni el contexto de arranque).
- La telemetría local y «obtener skills» al crear un agente vienen apagados; se encienden en Ajustes y en la creación.

**Arreglos**
- Windows: el menú de Workspace vuelve a abrirse solo al abrir la terminal. Con la configuración de fábrica de Windows, PowerShell bloqueaba su archivo de arranque y mostraba «la ejecución de scripts está deshabilitada en este sistema». Al actualizar, Workspace ajusta esa opción solo para tu usuario, al valor que recomienda Microsoft y sin pedir permisos de administrador. Si tu computadora la administra tu empresa y la tiene bloqueada, te lo dice. Después de actualizar, abre una terminal nueva.
- En Windows, desinstalar ya borra de verdad la carpeta de Workspace (antes decía «borrado» y la dejaba) y, si algo queda en uso, te lo dice.
- Pedir ayuda (`--help`) al instalador, al desinstalador o a cualquier comando muestra la ayuda y nunca ejecuta nada.
- `workspace uninstall --limpiar-todo` (o la pregunta al desinstalar) limpia también tus cerebros y los motores: quita solo lo que Workspace escribió en ellos (ajustes, permisos y archivos generados), con la lista exacta antes y un respaldo al lado de cada archivo que cambia; lo que editaste a mano se deja. Los perfiles de Workspace en OpenClaw y Hermes, con tus conversaciones de ahí, no se borran: se mueven a una carpeta de respaldo junto a cada uno.
- Desinstalar solo borra los comandos de terminal y los temas de Claude Code que puso Workspace (los reconoce por su marca) y te los nombra antes de confirmar. En Windows también borra sus comandos `.cmd`, aunque su carpeta no se llame «WORKSPACE».
- Desinstalar sin una terminal donde preguntarte (desde un script o un agente) ya no borra nada salvo que añadas `--yes`. Y si la carpeta de Workspace es un checkout de git con trabajo sin publicar (cambios sin commit o commits sin push), no la borra: desinstala lo demás y te dice qué tiene.
- Usuarios ya no reescribe un perfil que no entiende: conserva tus listas y campos propios, reconoce sin cambiarle la cédula un perfil guardado con el Bloc de notas, y uno que no se puede leer lo guarda entero aparte y deja uno nuevo con la misma cédula.
- Usuarios en un cerebro compartido entre máquinas: todas le dan al mismo usuario la misma cédula (antes era al azar y, al sincronizar, el perfil podía quedar con la de una máquina y sus pestañas con la de la otra). Una pestaña que quedó con una cédula de nadie se corrige sola al abrir el agente.
- Mac: reinstalar o actualizar aplica lo que elegiste para que la terminal abra el hub sola (en Windows ya era así), y el instalador dice cuál quedó.
- Documentación en Mac: si ninguna app abre un archivo, lo marca en Finder y te lo dice (antes decía «abierto» sin abrir nada).
- Hermes: el perfil propio de Workspace ya no copia las llaves de tu Hermes personal (solo tu modelo). La primera vez conecta el proveedor en Motores › Hermes › cuenta y proveedor; si ya tenías el perfil, sigue igual.
- Se acabó la nota «(cierre auto) — sesión cerrada sin captura manual» que llenaba la memoria de las pestañas.
- La «maleta» trae solo lo que tú escribiste (antes se colaban avisos del sistema de Claude Code, Codex y Antigravity).
- Las pestañas con nombre en coreano, chino, ruso u otro alfabeto tienen su propia memoria y ya no se mezclan.
- Codex: la conversación queda en su pestaña aunque abras el mismo cerebro en dos ventanas.
- Cargar un cerebro ya no le cambia el dueño ni esconde sus sesiones. Cargar o crear un agente ya no borra los comandos de terminal de tus otros agentes.
- Un agente cuyo nombre ya es un comando de tu computadora se rechaza al crearlo, y el instalador nunca pisa un comando que no es suyo.
- La agenda ya no se borra por un dato raro, y una imagen pegada va a la tarea abierta.
- Antigravity aparece como instalado aunque su instalador no lo haya puesto en el PATH.
- Windows: instalar e iniciar sesión en Codex y opencode desde Motores funciona; reinstalar respeta si elegiste que la terminal abra el hub sola, y el hub ya no se abre dentro de las terminales ocultas de los motores.
- Mac: tus agentes guardan memoria con el Python que trae la Mac (antes la forma indicada de guardar una nota fallaba con él).
- Mac: cerrar la ventana de la terminal deja que el motor cierre su sesión en orden, en vez de cortarlo de golpe.
- opencode 2: Workspace reconoce la conversación de cada pestaña al cerrar, así que la maleta trae lo que pasó en opencode y la pestaña retoma esa conversación (antes no la encontraba por un cambio de formato de opencode).
- OpenClaw en Mac: después de reiniciar la computadora ya no se queda esperando a un proceso que ya no existe, y nunca cierra otra aplicación por error.
- Memoria: una sección tuya cuyo título empieza con «Vigente» o «Historial» ya no se toca, y un archivo con caracteres que no se pueden leer bien no se reescribe: te avisa.
- `workspace update` te dice cuando no pudo actualizar (y sale con error) en vez de terminar como si todo estuviera bien, y al actualizar vuelve a ajustar los tiempos de los hooks.
- Ctrl+C al escribir el nombre de una sesión cancela sin mostrar un error.
- `workspace doctor` ya no se detiene a preguntarte rutas ni reinstala comandos de agentes que no tienen cerebro.

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
