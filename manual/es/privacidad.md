# Privacidad y transparencia

## Dónde viven tus cosas

| Qué | Dónde | Quién lo ve |
|---|---|---|
| El código de Workspace | su carpeta (`~/Workspace`, la que ya tenías —p. ej. `~/Desktop/Workspace`— o `%LOCALAPPDATA%\Workspace`) | es público |
| Tus ajustes, atajos, temas, estado | `~/.claude/workspace/` | solo tu máquina |
| Tus agentes y su memoria | la carpeta de cada cerebro | tú (y quien tú elijas si la sincronizas) |
| Tus credenciales | en esta máquina; jamás en el repositorio | solo tu máquina |

## Qué sale de tu máquina

Workspace **no tiene servidor propio** y no envía telemetría a nadie. Esta es la lista
completa de conexiones que puede hacer, a dónde y cuándo.

<!-- Lista verificada contra el código que viaja al cliente (todo lo que make-dist.sh no
quita): urllib, smtplib, socket, webbrowser, git fetch/pull, curl/irm y subprocesos a gh,
brew, npm y winget. Si agregas una conexión, agrégala aquí y en ../en/privacy.md. -->

**Siempre (la puedes apagar):**

| Conexión | A dónde | Cuándo | Cómo apagarla |
|---|---|---|---|
| Actualización automática (`git fetch` / `git pull`) | el repositorio de Workspace en GitHub | al abrir un agente, como mucho una vez cada 6 h (en «solo avisar», una vez al día y sin instalar) | `workspace update --auto off` (o la fila «automáticas» en Actualizaciones) |
| El programa de tu motor | el proveedor de ese motor (Anthropic, OpenAI, Google, AWS, GitHub, Cursor o el que conectes en OpenCode, OpenClaw o Hermes) | mientras usas el agente; también cuando Workspace le pregunta si tienes sesión iniciada | es el programa oficial con tu cuenta; se rige por las condiciones de ese proveedor |

**Cuando tú lo pides o lo activas:**

| Conexión | A dónde | Cuándo |
|---|---|---|
| `workspace update` y la sección **Actualizaciones** | GitHub, y el remoto git de cada cerebro que tenga uno | al pedirlo; también trae los cerebros que tengas en git |
| `workspace doctor` (sin `--check`) | GitHub (`git fetch`) | revisa si hay versión nueva de Workspace (y de los cerebros que tengas declarados en git) |
| Buscar *skills* en **Agregar agente** | `api.github.com` y `raw.githubusercontent.com` (repositorios públicos de Anthropic y OpenAI, y los que agregues); `skills.sh` solo si escribes una búsqueda en la comunidad | al llegar al plan del agente nuevo, solo si lo enciendes (viene apagado; se enciende en esa misma pantalla). GitHub recibe qué repositorios y archivos se consultan; el perfil de tu agente se compara en tu máquina |
| Instalar un motor | el instalador oficial: `claude.ai`, `chatgpt.com`, `antigravity.google`, `opencode.ai`, `openclaw.ai`, `hermes-agent.nousresearch.com`, `cli.kiro.dev`, `cursor.com`, npm (OpenCode en Windows; GitHub Copilot en Mac y Linux) o WinGet (GitHub Copilot en Windows) | solo cuando pides instalarlo |
| Revisión de skills (al abrir la siguiente sesión) | el proveedor del motor del agente, dentro de esa sesión visible (como cualquier mensaje) | solo en los agentes donde la prendiste (viene apagada); el agente lee la copia de la sesión anterior que Workspace guardó en el cerebro al cerrarla |
| Google Calendar | `calendar.google.com` (enlace iCal) o las APIs de Google (`accounts.google.com`, `oauth2.googleapis.com`, `www.googleapis.com`), solo lectura | si conectas tu calendario; después se refresca solo, en segundo plano |
| Correo (`workspace mail`) | el servidor SMTP que configures | cada vez que envías |
| Preparar el dictado por voz (macOS) | Hugging Face (modelo de whisper) y Homebrew | solo con `workspace voice --setup`; dictar es 100 % local |
| Proveedores por API (avanzado) | el endpoint que configures (p. ej. OpenAI, OpenRouter, Anthropic, Google, o uno local como Ollama o LM Studio) | solo si configuras un proveedor con tu clave de API |
| **Decisores** en la nube (Jev, OpenRouter, Liquid) | `api.typesafe.ai` (TypeSafe), `openrouter.ai` (OpenRouter) o `api.liquid.ai` (Liquid), con tu llave de cada uno; respeta `HTTPS_PROXY`/`NO_PROXY`. Con **Ollama** nada sale de esta computadora: va a `127.0.0.1:11434` (o al `OLLAMA_HOST` que fijes; si es otra máquina, Workspace avisa como con la nube), sin llave | solo si conectas uno en Motores → Modelos de decisión **y** enciendes un uso en Decisores (todo viene apagado), al **Probar** en Motores o al **Preguntar** a mano. Cada uso encendido manda su pregunta, sus opciones y un contexto mínimo: Memoria, el texto de la nota; Evals, el extracto del cierre de la sesión (hasta 4000 caracteres); Skills, el inicio de la sesión (hasta 6000); Seguridad, la ruta, los riesgos encontrados y lo escrito (hasta 1500), sin los comentarios ni docstrings que reconoce, solo si el escaneo ya encontró algo; los usos de agentes, lo que el agente mande (en Revisar, también lo que pediste). Preguntar manda el contexto que elijas (la pestaña, sesiones, la memoria o todo el cerebro), y `v` muestra antes qué archivos van. Antes de salir se quitan llaves, contraseñas y tokens (también los JWT); nunca salen los archivos privados (`privado: true` o una carpeta `privado/`), lo que es de otras personas en un cerebro compartido, chats, mensajes entre agentes ni bitácoras |
| Abrir un enlace | tu navegador | cuando eliges abrir algo (como la fuente oficial de un motor) |

## Lo que registra localmente

Para mostrarte qué hacen tus agentes, Workspace guarda en `~/.claude/workspace/` registros de
**actividad** (qué herramienta, cuándo, cuánto tardó, si salió bien) — **nunca el contenido**
de lo que el agente lee o escribe. No salen de tu máquina. Para apagarlos:
`WORKSPACE_NO_TELEMETRY=1`.

Al cerrar cada sesión, Workspace también anota en `~/.claude/workspace/metricas/` **números y
nombres** de esa sesión: tokens y modelo, cuánto duró, cuántas herramientas usó y cuántas
fallaron, qué skills leyó y cuántos archivos escribió. Jamás el texto de la conversación, y las
pestañas y archivos van como huellas, no por su nombre. **Workspace no los envía**: quedan en
esta computadora, en una carpeta que solo tu usuario puede abrir (en una PC de empresa, el
administrador del equipo también; en Windows lo cuidan los permisos de tu carpeta de usuario).
Se miden las sesiones de Claude Code, Codex, OpenCode, OpenClaw, Hermes, Antigravity, GitHub
Copilot, Cursor y Kiro, cada una con lo que su motor guarda (Cursor no anota horas, modelo ni
tokens; Kiro no guarda tokens); de Gemini, por ahora, solo cuándo fue cada sesión y cuánto duró.
Lo que un motor no da queda vacío, nunca en cero. `workspace metricas exportar` arma un archivo de solo totales,
sin personas, si tú decides compartirlo. `workspace metricas borrar --mio` borra lo tuyo. Para
apagarlas: `workspace metricas apagar`; `WORKSPACE_NO_METRICAS=1` las apaga de emergencia, y lo
que hagas mientras tanto no se mide nunca. Las métricas nunca se le pasan al agente.

Decisores anota cada pregunta en `~/.claude/workspace/decisions.jsonl`: el uso, la pregunta (sin
llaves, hasta 160 caracteres), las opciones, la respuesta, qué tan seguro estaba, cuánto tardó y
cuánto costó; del contexto, solo su nivel, cuántos tokens llevó y los nombres de las fuentes —
**nunca el contenido**. Ese archivo solo lo abre tu usuario (en Windows también: sus permisos son
solo tuyos y no heredan los de la carpeta) y, al pasar de unos 5 MB, se guarda una copia y se
empieza otro. No
sale de tu máquina. Con un uso encendido, Decisores además guarda en
`~/.claude/workspace/decisores/` la línea de tu última sesión hasta que la ves y, por cada
sesión, una huella (no el texto) de las instrucciones que recibió el agente; tampoco salen de
tu máquina. El hub, aunque Decisores esté apagado, anota en
`~/.claude/workspace/hub-novedades.json` solo la fecha en que te mostró por primera vez el
«nuevo» de su fila, para quitarlo a los 7 días.

**Conversaciones** no se conecta a ningún servidor. Cada sala vive en el cerebro del agente que
la abrió (carpeta `conversaciones/`), así que viaja con ese cerebro si lo sincronizas y la ve
quien comparta ese cerebro. Cada mensaje lleva quién lo escribió, en qué pestaña, con qué motor y
el nombre de su máquina; mientras un agente espera una respuesta, su cerebro guarda en
`msgs/_presencia/` que está escuchando. Lo que leíste en el hub y en qué orden te llegó cada
mensaje se queda en esta máquina, en `~/.claude/workspace/salas/`. Las salas no entran en la
búsqueda de memoria ni en el contexto que se manda a Decisores.

## Credenciales

Workspace **no lee ni copia** las credenciales de tus motores: cada programa oficial maneja su
propio login. Las claves que tú le des a Workspace (por ejemplo, para el correo, o la llave de
un modelo de decisión en Motores → Modelos de decisión) se guardan solo en esta máquina, fuera
de tu cerebro (no se sincronizan ni se suben a ningún lado), y los motores no las reciben.

**Dónde, según tu sistema:**

| Sistema | Dónde vive cada llave |
|---|---|
| macOS | en tu **llavero** (la app Llaves), con el programa `security` del sistema; la llave nunca va en la línea de comandos. Si el llavero está cerrado (por ejemplo, entrando por SSH), Workspace no abre ningún diálogo: guarda en el archivo y te lo dice en una línea |
| Windows | cifrada con tu cuenta de Windows (**DPAPI**), en un archivo con permisos solo tuyos: otra cuenta o una copia del archivo en otra PC no la abren |
| Linux | en el llavero de tu sesión con `secret-tool`, si está instalado, hay sesión abierta y el llavero está desbloqueado (Workspace solo lo mira: nunca te pide desbloquearlo ni crear uno); si no, en un archivo que solo tu usuario puede leer, y te lo dice en una línea |

La contraseña del correo (`workspace mail`) también se guarda así. En
`~/.claude/workspace/mail.json` quedan solo tu usuario y el servidor, con permisos solo tuyos.

La primera vez, Workspace pasa solo al llavero las llaves que ya tenías en el archivo: antes deja
un respaldo (cifrado con el mismo llavero), comprueba que cada una se lee de vuelta y recién
entonces las quita del archivo. Si algo falla, todo queda como estaba. Te avisa en una línea y se
deshace con `workspace migrate --undo 202611081500_boveda_al_llavero` (vuelven al archivo). La
contraseña del correo que tenías en `mail.json` pasa igual, sola: con respaldo y verificada antes
de quitarla de ahí; se deshace con `workspace migrate --undo 202611090000_correo_a_la_boveda`
(vuelve a `mail.json`). Si vuelves a una versión anterior con `workspace update --rollback`,
Workspace primero devuelve todo a donde estaba. El respaldo cifrado se borra solo a los 7 días
si todo se lee bien, y al desconectar una llave (o una cuenta de Google) se borran también sus
copias viejas.

Si el llavero no responde (cerrado, por SSH, o tardó demasiado), Workspace no abre ningún
diálogo: reintenta en unos minutos y te lo dice en una línea; mientras, lo que use esas llaves
dirá «sin llave». `workspace llaves` muestra cuáles no se pueden leer ahora.

- De fábrica, Workspace usa el modo automático, el recomendado: el llavero y, si no está, el
  archivo con aviso.
- `workspace llaves` dice de dónde sale cada llave (tu sistema, el llavero o el archivo), sin
  mostrar ninguna; `workspace llaves auditar` busca restos en texto plano en
  `~/.claude/workspace/` y deja los permisos solo para ti.
- Ningún valor de la bóveda aparece en lo que Workspace muestra o anota: el Historial, «d
  detalle» y lo que responde a los agentes lo tachan.
- A los motores que tienen reglas para eso, Workspace les niega leer la bóveda y pedirle una
  llave al llavero ([Compatibilidad](compatibilidad.md#tus-llaves-qué-motor-puede-leerlas)).

**Lo que no puede prometer:** el llavero protege tus llaves en el disco, en los respaldos (Time
Machine, Historial de archivos) y frente a otros usuarios, pero un programa que corre con tu
mismo usuario aún puede pedírselas. Por eso, crea en el sitio de cada proveedor una llave solo
para Workspace, con un tope de gasto.

Antes de publicar cada versión, un control automático revisa que no se cuele ninguna credencial
ni dato personal.

## Por qué así

Porque es tu computadora y tu trabajo. Ver [el manifiesto](../MANIFIESTO.md).
