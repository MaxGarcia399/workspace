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
brew y npm. Si agregas una conexión, agrégala aquí y en ../en/privacy.md. -->

**Siempre (la puedes apagar):**

| Conexión | A dónde | Cuándo | Cómo apagarla |
|---|---|---|---|
| Actualización automática (`git fetch` / `git pull`) | el repositorio de Workspace en GitHub | al abrir un agente, como mucho una vez cada 6 h (en «solo avisar», una vez al día y sin instalar) | `workspace update --auto off` (o la fila «automáticas» en Actualizaciones) |
| El programa de tu motor | el proveedor de ese motor (Anthropic, OpenAI, Google) | mientras usas el agente; también cuando Workspace le pregunta si tienes sesión iniciada | es el programa oficial con tu cuenta; se rige por las condiciones de ese proveedor |

**Cuando tú lo pides o lo activas:**

| Conexión | A dónde | Cuándo |
|---|---|---|
| `workspace update` y la sección **Actualizaciones** | GitHub, y el remoto git de cada cerebro que tenga uno | al pedirlo; también trae los cerebros que tengas en git |
| `workspace doctor` (sin `--check`) | GitHub (`git fetch`) | revisa si hay versión nueva de Workspace (y de los cerebros que tengas declarados en git) |
| Buscar *skills* en **Agregar agente** | `api.github.com` y `raw.githubusercontent.com` (repositorios públicos de Anthropic y OpenAI, y los que agregues); `skills.sh` solo si escribes una búsqueda en la comunidad | al llegar al plan del agente nuevo, solo si lo enciendes (viene apagado; se enciende en esa misma pantalla). GitHub recibe qué repositorios y archivos se consultan; el perfil de tu agente se compara en tu máquina |
| Instalar un motor | el instalador oficial: `claude.ai`, `chatgpt.com`, `antigravity.google` o npm | solo cuando pides instalarlo |
| Revisión de skills (al abrir la siguiente sesión) | el proveedor del motor del agente, dentro de esa sesión visible (como cualquier mensaje) | solo en los agentes donde la prendiste (viene apagada); el agente lee la copia de la sesión anterior que Workspace guardó en el cerebro al cerrarla |
| Google Calendar | `calendar.google.com` (enlace iCal) o las APIs de Google (`accounts.google.com`, `oauth2.googleapis.com`, `www.googleapis.com`), solo lectura | si conectas tu calendario; después se refresca solo, en segundo plano |
| Correo (`workspace mail`) | el servidor SMTP que configures | cada vez que envías |
| Preparar el dictado por voz (macOS) | Hugging Face (modelo de whisper) y Homebrew | solo con `workspace voice --setup`; dictar es 100 % local |
| Proveedores por API (avanzado) | el endpoint que configures (p. ej. OpenAI, OpenRouter, Anthropic, Google, o uno local como Ollama o LM Studio) | solo si configuras un proveedor con tu clave de API |
| Abrir un enlace | tu navegador | cuando eliges abrir algo (como la fuente oficial de un motor) |

**Solo dentro de tu máquina:** `workspace proyectos` abre, de fábrica, un panel web local en `127.0.0.1`;
no se puede abrir desde otra computadora.

## Lo que registra localmente

Para mostrarte qué hacen tus agentes, Workspace guarda en `~/.claude/workspace/` registros de
**actividad** (qué herramienta, cuándo, cuánto tardó, si salió bien) — **nunca el contenido**
de lo que el agente lee o escribe. No salen de tu máquina. Para apagarlos:
`WORKSPACE_NO_TELEMETRY=1`.

## Credenciales

Workspace **no lee ni copia** las credenciales de tus motores: cada programa oficial maneja su
propio login. Las claves que tú le des a Workspace (por ejemplo, para el correo) se guardan
solo en esta máquina. Antes de publicar cada versión, un control automático revisa que no se
cuele ninguna credencial ni dato personal.

## Por qué así

Porque es tu computadora y tu trabajo. Ver [el manifiesto](../MANIFIESTO.md).
