# Privacidad y transparencia

## Dónde viven tus cosas

| Qué | Dónde | Quién lo ve |
|---|---|---|
| El código de Workspace | su carpeta (`~/Desktop/Workspace` o `%LOCALAPPDATA%\Workspace`) | es público |
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
| **Decisores** con Jev | `api.typesafe.ai` (TypeSafe), con tu llave de TypeSafe; respeta `HTTPS_PROXY`/`NO_PROXY` | solo si conectas Jev en Motores → Modelos de decisión **y** enciendes un uso en Decisores (todo viene apagado), al **Probar** en Motores o al **Preguntar** a mano. Cada uso encendido manda su pregunta, sus opciones y un contexto mínimo: Memoria, el texto de la nota; Evals, el extracto del cierre de la sesión (hasta 4000 caracteres); Skills, el inicio de la sesión (hasta 6000); Seguridad, la ruta, los riesgos encontrados y lo escrito (hasta 1500), sin los comentarios ni docstrings que reconoce, solo si el escaneo ya encontró algo; los usos de agentes, lo que el agente mande (en Revisar, también lo que pediste). Preguntar manda el contexto que elijas (la pestaña, sesiones, la memoria o todo el cerebro), y `v` muestra antes qué archivos van. Antes de salir se quitan llaves, contraseñas y tokens (también los JWT); nunca salen los archivos privados (`privado: true` o una carpeta `privado/`), lo que es de otras personas en un cerebro compartido, chats, mensajes entre agentes ni bitácoras |
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
tu máquina.

## Credenciales

Workspace **no lee ni copia** las credenciales de tus motores: cada programa oficial maneja su
propio login. Las claves que tú le des a Workspace (por ejemplo, para el correo, o la llave de
Jev en Motores → Modelos de decisión) se guardan solo en esta máquina, en un archivo que solo lee
tu usuario (en Windows, con permisos propios desde la 0.8.0: antes heredaba los de la carpeta
`.claude`), y los motores no las reciben. Antes de publicar cada versión, un control automático revisa que no se
cuele ninguna credencial ni dato personal.

## Por qué así

Porque es tu computadora y tu trabajo. Ver [el manifiesto](../MANIFIESTO.md).
