# Novedades de Workspace

Qué cambia en cada versión, contado desde tu lado de la pantalla. La versión
que tienes la ves con `workspace version` (y abajo a la derecha en el hub).
English: [CHANGELOG.en.md](CHANGELOG.en.md).

Cómo leer esto: cada versión tiene su número (`MAYOR.MENOR.PARCHE`). Un
cambio de PARCHE arregla cosas; uno de MENOR trae funciones nuevas sin romper
nada; uno de MAYOR avisa con tiempo si algo cambia de forma.

## 0.8.1 — 2026-11-07

**Novedades**
- **Decisores se ve en el hub, junto a tus agentes.** Debajo de ellos va la
  fila «◆ Decisores», con el modelo de decisión activo donde un agente lleva
  su motor (por ejemplo, «Jev»). Sin modelo dice «nuevo» durante 7 días
  (desde la primera vez que tu hub la muestra) y después «configurar»; Enter
  te lleva a Motores → Modelos de decisión para conectar uno. Con un modelo,
  Enter abre Decisores y ← → cambian el modelo activo entre los que están
  listos y «apagado» (se guarda igual que en Decisores → Ajustes). El `0` la
  abre desde el inicio del hub, como las cifras 1-9 abren a tus agentes.
  Prender el modelo no prende ningún uso: esos se eligen en Decisores.

**Arreglos**
- **Una pestaña ya no reabre una conversación vieja después de que Claude
  Code la bifurca** (por ejemplo, al mandar la conversación al fondo): la
  pestaña pasa a la conversación nueva y el hub la reabre ahí. Si usas
  `/fork` y sigues escribiendo en la original, la pestaña vuelve a ella. Las
  listas de pestañas muestran una sola fila por pestaña, con la conversación
  que de verdad abre.
- **Memoria distingue mejor lo que ya terminaste.** Una nota contada en
  pasado («probé…», «corregí…», «instalé…») se marca como «hecho» con más
  seguridad, en vez de quedarse como «nota».
- **Revisar compara contra lo que pediste y no le cree al entregable lo que
  dice de sí mismo:** un reporte que dice «los 8 usos están verificados» con
  dos pendientes ya no sale «completo», y una parte que pediste y quedó
  pendiente cuenta como faltante. Con reportes largos todavía puede dudar:
  sirve mejor en «sugiere».
- **`workspace decidir` dice cuánto tardó el modelo en responder** (`ms`, el
  mismo número que queda en el Historial); antes ese dato no venía.

## 0.8.0 — 2026-11-07

**Novedades**
- **Decisores, una sección nueva que viene apagada.** Un modelo de decisión no
  conversa ni escribe: elige entre opciones fijas y dice qué tan seguro está.
  Hoy hay uno, **Jev** (de TypeSafe, en la nube). Se conecta una sola vez, en
  **Motores → Modelos de decisión**: pegas tu llave de TypeSafe y lo pruebas.
  Su uso lo cobra TypeSafe con tu cuenta; en Preguntar ves antes cuántos
  tokens lleva cada pregunta (también lo fijo que lleva aunque no mandes
  contexto) y un costo aproximado.
- **Dónde puede ayudar.** Cada uso tiene su nivel (apagado · observa ·
  sugiere · decide) y todos empiezan apagados:
  - en Workspace: el tipo de una nota de memoria, cómo terminó una sesión
    (Evals), si una sesión amerita una skill y qué tan riesgoso es algo que un
    agente escribió (Seguridad: en Claude Code, solo cuando el escaneo ya
    encontró un riesgo);
  - para tus agentes: elegir entre opciones, revisar si un entregable quedó
    completo, escoger la mejor de varias instrucciones y repartir trabajo
    entre agentes. En GitHub Copilot, Cursor, Kiro y Antigravity el agente usa
    la herramienta `decidir`; en Claude Code, Codex y los demás, el comando
    `workspace decidir --stdin` (un JSON por la entrada estándar, como explica
    su ayuda), que pide permiso como cualquier otro comando.
  - «Sugiere» solo muestra la respuesta; «decide» la aplica solo si supera tu
    umbral, y nunca si el modelo no dijo qué tan seguro estaba. Si el modelo
    falla o tarda, todo sigue como si Decisores no existiera.
- **Tres usos con reglas propias.**
  - **Seguridad solo puede subir el riesgo, nunca bajarlo:** en «decide» solo
    aplica «alto»; «medio» o «bajo» quedan como sugerencia y el aviso del
    escaneo sigue entero. Juzga solo el código: antes de preguntarle se le
    quitan los comentarios y los docstrings, para que lo que diga el archivo
    no lo convenza.
  - **Revisar** recibe aparte lo que pediste y lo que se entregó: lo que el
    entregable deja pendiente y no estaba en el pedido no cuenta como
    faltante. Con reportes largos todavía puede dudar: sirve mejor en
    «sugiere».
  - **Skills en «decide»**, cuando el modelo está seguro (en tu umbral o más), ya no
    espera las 2 horas entre revisiones: si dice que la sesión amerita una
    skill, la revisión llega (nunca dos en menos de 10 minutos); si dice que
    no, no llega. Por debajo de tu umbral, y en «observa» y «sugiere», esas 2
    horas siguen mandando.
- **Ves lo que hace**, con un uso en «sugiere» o «decide» («observa» no
  muestra nada):
  - cuando el modelo de decisión interviene, el agente te lo dice en el chat
    con un bloque ◆ al final de su respuesta, una línea por intervención: qué
    hizo, qué tan seguro estaba y si se aplicó o solo se sugirió. Cada línea
    lleva el nombre del modelo que respondió (con Jev: «◆ Jev: tabla · 87 % ·
    sugerido») y le llega al agente con el recordatorio de mostrártela, así
    que no depende de lo que recuerde de su arranque;
  - al guardar una nota, Memoria lo dice solo si sugiere o aplica otro tipo
    («◆ Jev: guardé la nota como hecho · 88 % · aplicado»); en Claude Code,
    la línea de Seguridad aparece en la conversación junto al aviso, y lo que
    el agente no vio en su turno le llega en tu siguiente mensaje;
  - al abrir la siguiente sesión, una línea dice qué opinó de la anterior
    (Evals y Skills), una sola vez;
  - Historial dice qué cambió cada decisión («nota → hecho», «aviso → alto») y
    cuántas hubo hoy; junto al umbral de cada uso ves sus últimas confianzas;
  - la barra de estado de Workspace suma «◆ Decisores: hoy 7 · 1 aplicada» (Claude
    Code, GitHub Copilot, Cursor y Antigravity);
  - en Claude Code, si cambias un uso de agentes a media sesión, el agente se
    entera en tu siguiente mensaje; en los demás motores, al abrir otra sesión.
- **Preguntar**, para probarlo a mano con el contexto que elijas: nada, la
  pestaña, algunas sesiones, la memoria o todo el cerebro. Con `v` ves qué
  archivos irían (nunca su contenido) y cuántos quedaron fuera. **Historial**
  muestra qué se preguntó y qué respondió el modelo, y ahí calificas si
  acertó; ese registro se queda en tu computadora.
- **Lo que sale de tu computadora, y solo con un uso encendido:** la pregunta,
  sus opciones y un contexto mínimo van a TypeSafe. Antes de salir se quitan
  llaves, contraseñas y tokens (también los JWT). Con Memoria o Cerebro no
  salen tus archivos privados
  (`privado: true` o una carpeta `privado/`), lo que es de otras personas en
  un cerebro compartido, ni chats, mensajes entre agentes o bitácoras. La
  primera vez que Preguntar manda contenido del cerebro, la respuesta te lo
  avisa. Con todo apagado no sale nada y tus agentes ven lo mismo que antes.
- **Motores ahora tiene dos cuadritos:** Motores de agentes (la pantalla de
  siempre) y Modelos de decisión.
- Prender o apagar un uso de agentes cambia solo lo de Workspace en la
  configuración de Kiro y Cursor del cerebro, sin respaldos ni avisos; con
  todo apagado queda igual que en la 0.7.0.

**Arreglos**
- **En Windows, la bóveda con tus llaves y los archivos locales de Decisores
  ya solo los puede leer tu usuario** (y el sistema). La bóveda, con todas
  las llaves que le das a Workspace (la del correo, la de tu modelo de
  decisión…), ya estaba en la 0.7.0
  y heredaba los permisos de la carpeta `.claude`: en una PC, eso dejaba
  leerla a otra cuenta (la del sandbox de Codex).
- **En Windows, Ctrl+C dentro de una sección del hub ya no lo cierra:** vuelve
  al menú. Antes el hub se cerraba con un error.
- En Windows, en Decisores, Modelos de decisión y la puerta de Motores:
  Shift-Tab vuelve a la pestaña anterior, los signos ¿ ¡ « » € llegan bien
  aunque escribas por SSH y, sin una consola de verdad, las pantallas muestran
  su vista y terminan en vez de quedarse esperando.

## 0.7.0 — 2026-11-06

**Novedades**
- **Workspace empieza a llevar, en tu computadora, el registro de cómo
  trabajan tus agentes.** Al cerrar cada sesión anota solo números y nombres:
  cuánto duró, tokens y modelo, el costo cuando el motor lo da, cuántas
  herramientas fallaron, interrupciones y qué skills leyó el agente. Nunca el
  texto de la conversación; las pestañas y los archivos van como huellas, no
  por su nombre. **Workspace no los envía a nadie**: quedan en
  `~/.claude/workspace/metricas/`, en una carpeta que solo tu usuario puede
  abrir (en Windows, dentro de tu perfil de usuario). Es la base de la sección de desempeño que llegará después: así, ese
  día ya habrá semanas de historia. Las sesiones que ya tenías se miden poco
  a poco al cerrar las nuevas, sin hacerte esperar.
  - Mide Claude Code, Codex, OpenCode, OpenClaw, Hermes, Antigravity, GitHub
    Copilot, Cursor y Kiro. Cada motor da lo que guarda: Cursor no anota
    horas, modelo ni tokens, y Kiro no guarda tokens (solo sus créditos); lo
    que un motor no da queda vacío, nunca en cero. De Gemini, por ahora, anota
    solo cuándo fue cada sesión y cuánto duró.
  - Funciona igual en Mac y en Windows (también con acentos o «ñ» en tu
    nombre de usuario).
- **Un aviso de una línea, una sola vez**, en el menú o al abrir un agente,
  te dice qué se guarda y cómo verlo, apagarlo o borrarlo.
- **`workspace metricas`** (o `workspace metrics`): `estado`, `salud`,
  `importar` (mide de una vez la historia de esta computadora), `exportar
  --json <archivo>` (solo totales, sin personas, por si decides compartirlo),
  `borrar --mio`, `borrar --todo` o `borrar --antes AAAA-MM`, `apagar` y
  `encender`. También se apaga en Ajustes («Métricas de desempeño»). Lo que
  hagas con las métricas apagadas no se mide nunca, tampoco al volver a
  encenderlas. Si algún archivo no se puede borrar (en Windows, porque otro
  programa lo tiene abierto), `borrar` te dice cuál en vez de darlo por
  borrado.
- **Las métricas nunca se le pasan al agente**: no las ve mientras trabaja.
- El paquete de diagnóstico (`workspace doctor --bundle`) incluye la salud de
  las métricas, solo con números.

**Arreglos**
- **En Windows, Motores ya reconoce tu sesión de GitHub Copilot.** Copilot
  guarda la cuenta en su archivo de configuración cuando no hay llavero, y
  Workspace no sabía mirarlo: salía «no se pudo verificar» con la sesión
  abierta. Ahora mira solo si hay usuario; tu token nunca se usa, guarda ni muestra.
- **Con GitHub Copilot, el inicio y el cierre de cada sesión ya corren una
  sola vez.** Copilot también lanza los avisos de inicio, de cada mensaje y
  de cierre que Workspace prepara para Claude Code, así que el tono, la
  memoria de la pestaña, el respaldo de la conversación y la revisión de
  skills se hacían dos veces. Ahora Workspace reconoce esos avisos repetidos
  y no hace nada con ellos.
- **En Windows, con acentos o «ñ» en tu nombre de usuario, la memoria, el
  respaldo y los demás pasos del cierre encuentran tu cerebro y tu
  conversación.** Antes leían la ruta con la codificación vieja de la
  consola («JosÃ©» en vez de «José») y, en algunos motores, no encontraban
  nada que guardar.
- **En Windows, la barra de Antigravity y la de los agentes que crees desde
  ahora ya no salen vacías** cuando la carpeta lleva ciertos acentos (por
  ejemplo «Á»). La barra de los agentes que ya tenías queda como estaba.
- **En Windows, las métricas de Hermes, OpenClaw y OpenCode ya no se pierden
  con un cerebro en una ruta larga** (por ejemplo en la
  carpeta Documentos de OneDrive). Windows no deja escribir rutas de más de 260
  caracteres, y el archivo de números que Workspace guarda junto al respaldo
  pasaba de ese límite: la sesión quedaba sin tokens ni costo. Ahora se
  escribe y se lee igual, sin cambiar ninguna configuración de tu Windows.
- **En Windows, dos agentes que cierran a la vez ya no se borran el registro
  uno al otro.** Si los cierres coincidían, una línea podía perderse o quedar
  partida; ahora cada una se agrega completa.

## 0.6.0 — 2026-11-06

**Novedades**
- **Tres motores nuevos: GitHub Copilot, Cursor y Kiro.** Se instalan desde
  Motores y abren tus agentes con tu cuenta, sobre el mismo cerebro que tus
  otros motores: leen el mismo `AGENTS.md`, cada pestaña retoma su
  conversación y, al cerrar, Workspace arma la maleta como con los demás.
  Probados en vivo en la Mac y en Windows 11 (en Linux falta probarlos).
  - **GitHub Copilot** (`copilot`, el CLI oficial de GitHub) corre con tu
    suscripción y el modelo de tu cuenta. En su configuración Workspace solo
    escribe su barra (con una copia del archivo antes); lo demás va en cada
    arranque. Un agente no lee las conversaciones de otro: el buscador de
    sesiones de Copilot es uno para toda tu cuenta y Workspace lo apaga en
    cada arranque (si pasas tus propias `--excluded-tools`, ganan las tuyas).
    Se instala con npm en Mac y Linux y con WinGet en Windows (en la Mac, no
    con el de Homebrew: macOS lo retiene y muestra un aviso que no se
    cierra). En Windows, Copilot también corre los ganchos que Workspace deja
    en tu cerebro, así que cada gancho trae ahora su versión para PowerShell:
    al actualizar se reescriben solos (si no, `workspace doctor` lo hace).
  - **Cursor** (`cursor-agent`) usa el modelo que elijas en Cursor. En sus
    ajustes (`cli-config.json`) Workspace solo agrega su barra, y en cada
    arranque le dice que confíe en la carpeta de tu cerebro (la marca queda
    en la carpeta de Cursor, no en tu cerebro). En la Mac, instálalo desde
    Motores: el paquete de Homebrew no arranca. En Windows arranca y usa sus
    herramientas aunque abras Workspace desde Git Bash. Lo que Workspace
    supone de Cursor sale de su documentación oficial o de probar el
    programa, nunca de su código (los términos de Cursor lo piden).
  - **Kiro**, el agente de terminal de AWS (`kiro-cli`, antes Amazon Q
    Developer CLI), versiones 2 y 3, usa el modelo que elijas en Kiro. En
    cada arranque le pide confiar en la carpeta de tu cerebro, sin
    guardarlo, y en `~/.kiro` no escribe nada: su agente vive en tu cerebro
    (`.kiro/agents/workspace.json`). Si no has iniciado sesión, te lo ofrece
    antes de abrir. Su barra es la suya, sin tocar: si quieres ver tu uso y
    tus créditos, préndelos en `/settings display` dentro de Kiro.
- **Copilot, Cursor, Kiro y Antigravity guardan la memoria sin pedirte
  permiso, y la terminal sigue preguntando.** El agente guarda con una
  **herramienta de memoria** de Workspace (MCP: `guardar_nota`,
  `guardar_resumen` y `ver_memoria`), no con un comando de terminal: el
  motor la aprueba por su nombre y ninguna terminal lee el texto de la nota,
  así que no hay forma de colar otro comando en él. La herramienta solo
  escribe en la pestaña de la ventana que la abrió: ni otro cerebro ni otra
  pestaña. Copilot la recibe en cada arranque (nada se escribe en su
  configuración); Cursor y Antigravity, en la configuración de proyecto de
  tu cerebro (`.cursor/` y `.agents/mcp_config.json`); y Kiro, en el agente
  `workspace` de tu cerebro, que se elige al abrir (si eliges otro agente en
  Kiro, gana el tuyo). En Antigravity reemplaza el comando de memoria que
  Workspace aprobaba hasta ahora: desde su versión 1.5.1, Antigravity
  aprueba por el principio del comando, así que ese permiso también corría
  lo que se escribiera detrás. Ese permiso se quita solo al abrir, y tus
  reglas de Antigravity se quedan tal cual; si pasas tu propio
  `--settings`, gana el tuyo y la memoria te pide permiso. Si la
  herramienta falla, el agente te avisa en vez de escribir la memoria a
  mano, y funciona aunque Workspace corra desde un entorno virtual de
  Python que luego borres. Probado en vivo en la Mac y, con Copilot, Cursor
  y Kiro, en Windows 11 (Antigravity en Windows falta probarlo).
- **Tus pestañas son las mismas en todas tus máquinas.** Ahora cada máquina
  sabe quién eres en todos tus cerebros: se lo dices una vez (o lo toma de lo
  que ya tenías) y no adivina con la carpeta de otra persona. La lista de
  pestañas sale solo del cerebro, así que lo que una máquina tenía guardado
  aparte (pruebas viejas, pestañas quitadas) ya no aparece ni regresa. Si en
  un cerebro eras dos usuarios (un nombre viejo y uno nuevo), se juntan solos
  sin borrar nada; `workspace identidad deshacer` lo devuelve todo, también
  las pestañas de tu nombre anterior, y la siguiente apertura no vuelve a
  juntarlos.
- **Archivar pestañas sin borrarlas.** En el menú de pestañas, `a` archiva la
  marcada y `u` deshace; al final queda «Archivadas (N)» para recuperarlas.
  Las que no abres en 15 días se archivan solas (ajuste
  `sesiones.archivar_dias`; 0 lo apaga), con un aviso de una línea que
  siempre muestra «u para deshacer». El archivado viaja: sale del menú en
  todas tus máquinas, y abrirla la regresa. Después de actualizar hay 15
  días de gracia antes del primer archivado, y una máquina que llega con el
  cerebro desactualizado no archiva nada. También desde la terminal:
  `workspace sesiones lista|archivar|desarchivar`.
- **Workspace avisa si tu cerebro no está sincronizando.** Cada máquina deja
  una constancia pequeña en el cerebro (`STATE/maquinas/`), y si otra máquina
  lleva días sin noticias, si Obsidian está cerrado o si hay archivos en
  conflicto, te lo dice en una línea al abrir el agente y en `workspace doctor`.
- **Llevar la conversación de Claude Code a tu otra máquina (opcional,
  apagado de fábrica).** Se prende por cerebro con `workspace sesiones
  conversacion on` (y vale para todas las máquinas y personas que lo usan): al
  cerrar una pestaña su conversación se guarda comprimida en el cerebro y en
  tu otra máquina se retoma tal cual; al abrir solo se trae la tuya. En un
  cerebro compartido, todos los que lo usan pueden ver esas conversaciones:
  para privacidad, usa un cerebro aparte. No sube si pesa más del tope
  (`sesiones.conversacion_max_mb`, 4 MB) o si trae algo que parece una llave,
  y nunca va a git. Con Obsidian Sync, prende «Sync all other types» en cada
  dispositivo.
- **GitHub Copilot y Kiro escriben en el cerebro de su agente sin
  preguntarte**, como los demás motores, si el agente tiene «su cerebro sin
  preguntar» (lo de fábrica; se cambia en Agentes). Fuera del cerebro
  (también en una carpeta hermana de nombre parecido) siguen preguntando, y
  la terminal pregunta como siempre; con la opción apagada, preguntan antes
  de cada archivo. No se escribe nada en la configuración de Copilot ni de
  Kiro: en Copilot va en cada arranque (si pasas tus propios permisos,
  `--allow-tool`, `--yolo`…, ganan los tuyos) y en Kiro, en el agente de tu
  cerebro. Si la ruta del cerebro lleva paréntesis, Copilot no acepta la
  regla y sigue preguntando (te lo dice al abrir). Probado en vivo en la
  Mac; en Windows falta probarlo.
- **El agente no puede tocar la configuración de ningún motor ni de git u
  Obsidian dentro de su cerebro.** Tu cerebro lo comparten todos tus motores,
  git y Obsidian, y cada uno carga su configuración de ahí al abrir (hooks,
  servidores MCP, agentes, plugins): un motor que escribiera la de otro
  podría darse permisos o dejar un comando que corre después. Ahora, cuando
  el agente escribe en su cerebro sin preguntar, ninguno de sus motores
  (Claude Code, Antigravity, Copilot, Cursor ni Kiro) puede escribir con sus
  herramientas de archivos en `.git/`, `.github/`, `.agents/`, `.cursor/`,
  `.kiro/`, `.codex/`, `.gemini/`, `.vscode/`, `.obsidian/`, `.opencode/`,
  `opencode.json`, `.mcp.json` ni en los ajustes, skills, agentes, comandos y
  hooks de `.claude/` (tampoco con mayúsculas, como `.KIRO/`). Se niega, no
  te pregunta (en Claude Code, antes te preguntaba): si quieres cambiar esa
  configuración, hazlo tú. Tus notas, skills y documentos del cerebro se
  escriben igual, y Workspace sigue escribiendo lo suyo ahí. En Claude Code
  la regla queda en la configuración del cerebro, junto al permiso de
  escribir en él: vale también si lo abres fuera de Workspace (VS Code, la
  app de escritorio o `claude` a secas), y tus cerebros la reciben solos al
  actualizar. Si en Antigravity no se puede poner (pasas tu propio
  `--settings` o su archivo de ajustes no se puede leer), te pregunta antes
  de editar y te lo dice al abrir. En Windows, con una ruta de cerebro muy
  larga, GitHub Copilot pregunta antes de escribir (las reglas no cabrían en
  la línea de comandos) y te lo dice al abrir. Codex, opencode, OpenClaw y
  Hermes no cambian: usan su propia protección. Probado en vivo en la Mac;
  en Windows falta probarlo.
- **Tu configuración de proyecto se respeta: Workspace solo agrega lo suyo.**
  En `.agents/mcp_config.json` (Antigravity) y en `.cursor/mcp.json` y
  `.cursor/cli.json` (Cursor) de tu cerebro, Workspace pone solo su servidor
  de memoria y sus reglas: tus servidores (por ejemplo, `github`) y tus
  permisos se quedan tal cual, y el archivo conserva sus permisos. Si alguien
  cambió lo de Workspace, se restaura solo eso (con respaldo) y te avisa en
  una línea. Si esa carpeta es un enlace (por ejemplo, a tus skills
  compartidas) o el archivo no se puede leer, no lo toca: la memoria te pide
  permiso y te lo dice al abrir. Tu `.gitignore` ignora esos archivos.
- **Motores dice si Antigravity va completo o «experimental».** Google no
  soporta usar Antigravity dentro de otras apps con un plan personal
  (https://antigravity.google/docs/faq/). Con una API key de Gemini o una
  cuenta empresarial (proyecto de Google Cloud), Motores dice «completa». Si
  entras con tu cuenta de Google, como Antigravity no dice si el plan es
  personal, dice «experimental» y explica por qué. Todo funciona igual: es
  solo el aviso.
- **Textos más claros sobre los motores.** El README, el manual y la ayuda de
  Motores (tecla `i`) dicen lo que hace Workspace: configura y abre tus
  motores oficiales, con tu cuenta. También avisan que Workspace no está
  afiliado a las empresas de los motores, y el mapa del README ya muestra los
  nueve. Las pantallas y los mensajes ya solo dicen «motor» o «Workspace»
  (antes usaban un término técnico en inglés).

**Arreglos**
- **En Windows, la barra de Antigravity y la de Cursor se ven aunque tu
  usuario de Windows tenga espacios** (por ejemplo «Ana Lopez»). Antes la
  terminal recortaba las comillas del comando y la barra no salía; ahora la
  carpeta va con su nombre corto de Windows. En Mac y Linux nada cambia.
- **En Windows, un motor que se cuelga ya no deja procesos vivos.** Si Workspace
  tiene que cortar a un motor que no responde (al revisar tu cuenta, su versión
  o un turno sin ventana), ahora cierra también los programas que ese motor
  abrió por debajo, en vez de quedarse esperando. En Mac y Linux nada cambia.
- **Los avisos de una línea al abrir un agente ya se ven** (por ejemplo,
  «Workspace actualizado a v…», y los nuevos de usuarios juntados, cerebro
  sin sincronizar y pestañas archivadas): salen debajo del banner, justo
  antes del chat. Antes el banner limpiaba la pantalla y los borraba. Vale
  para todos los motores.
- **Una pestaña de Codex vuelve a retomar después de un cierre a la mala.**
  Si Workspace se cerraba de golpe (un crash o un `kill -9`; no al cerrar la
  ventana), el motor se quedaba abierto en segundo plano, y Codex no deja
  retomar una conversación mientras otro proceso la tiene abierta: al
  reabrir la pestaña empezabas de cero. Ahora Workspace cierra ese motor al
  momento, como si cerraras la ventana (le da unos segundos para guardar), y
  si no alcanzó, al reabrir cierra primero todos los motores que quedaron
  vivos y después retoma. Vale para todos los motores. Mac y Linux; en
  Windows falta probarlo.
- **Claude Code: la maleta ya no se pierde si el programa se cierra de
  golpe.** Workspace la armaba solo al cerrar la sesión; con un crash (un
  `kill -9`, la máquina colgada, se fue la luz) la pestaña se quedaba sin
  maleta hasta el siguiente cierre normal. Ahora se refresca al terminar cada
  respuesta (sin IA y sin que lo notes: tarda milisegundos), así que trae
  hasta la última. El cierre de siempre sigue haciendo lo demás.
- **Hermes 0.22.5 vuelve a funcionar como antes.** Desde esa versión Hermes
  nombra distinto sus conversaciones y Workspace no las encontraba al
  cerrar: la pestaña empezaba de cero y la maleta quedaba vacía. Ahora
  retoma cada pestaña y arma su maleta; cada pestaña guarda su memoria en la
  suya (Hermes corre todas las conversaciones en un solo proceso de fondo y
  una nota de otra pestaña, u otro agente, podía caer en la primera), y un
  `/resume` dentro de Hermes, después de conversar, se respeta al cerrar.
- **Quitar un agente o desinstalar limpia lo que Workspace dejó en tus
  motores, y solo eso.** Quitar un agente desde Agentes ahora también quita
  la confianza que Workspace le dio a su cerebro en Codex y en Antigravity
  (antes solo lo hacía la desinstalación) y la herramienta de memoria de su
  cerebro. Desinstalar quita además las barras de Copilot y Cursor con sus
  comandos, la copia de la configuración de Copilot y las marcas de
  confianza que dejó Workspace. Se quita solo lo que escribió Workspace, tal
  cual lo escribió: lo que pusiste tú, otros agentes (también si comparten
  el cerebro) y tus otras carpetas se quedan; un archivo o carpeta se borra
  solo si queda vacío, y lo que se edita conserva sus permisos.
- **En Windows, instalar un motor desde Motores ya no lo bloquea Microsoft
  Defender.** Defender marcaba como troyano el comando de una línea que baja
  el instalador y lo corre al mismo tiempo, y no se instalaba nada. Ahora
  Workspace baja primero el instalador oficial (solo por HTTPS), lo corre
  como archivo en la misma terminal y lo borra al terminar; si no se pudo
  bajar, te lo dice en una línea y no corre nada. Vale para Claude Code,
  Codex, Antigravity, OpenClaw, Hermes, Kiro y Cursor; en Mac y Linux nada
  cambia. Además, el cierre del instalador nombra los nueve motores.
- En Windows, guardar en el cerebro ya no falla en silencio cuando el
  antivirus u Obsidian tienen el archivo abierto: se reintenta y, si no se
  puede, avisa (antes podía perderse un mensaje o una nota).

## 0.5.1 — 2026-10-21

**Arreglos**
- **El mapa de la memoria sale de la portada del hub**, donde se confundía
  con tus agentes, y queda en Documentación: ábrelo con su primer renglón o
  con la tecla `m`. Funciona como siempre: con el agente elegido ahí, Tab
  cambia de agente y Esc te regresa a los capítulos.
- **Sin agentes, la primera flecha ↓ de la portada ya mueve el cursor.**
  Antes se quedaba en Menú y había que oprimirla otra vez.
- **Hermes guarda en el cerebro las skills que aprende.** Van a
  `skills/aprendidas/` de tu agente y ya no a su perfil compartido: un agente
  no ve lo que aprendió otro, y al cerrar la sesión Workspace las anota en el
  catálogo del cerebro para que tus otros motores también las usen.
- **Hermes ya no te pide aprobar el gancho de Workspace al abrir.** Si tienes
  ganchos propios en su perfil, te sigue preguntando como antes.
- **Hermes recibe la memoria larga de tu cerebro** (`STATE/MEMORY.md`) al
  empezar una conversación, como tus otros motores: ya no depende de que el
  agente decida leerla. Al retomarla le llega otra vez solo si cambió, así
  que no se acumula en la conversación cada vez que la reabres.
- **Desde Discord, Telegram, Slack, WhatsApp u otra plataforma de
  mensajería, Hermes ya no puede buscar en las conversaciones de tus otros
  agentes.** Workspace apaga ahí su búsqueda de conversaciones y su memoria
  propia, como ya lo hacía en la terminal.
- **Dos pestañas del mismo agente ya no se borran la memoria.** Al cerrar una
  (en OpenClaw, Hermes, Codex u OpenCode), el bloque de memoria se queda
  mientras la otra siga abierta, y la última en cerrar lo limpia aunque no
  sea la que lo escribió.
- **Con dos pestañas del mismo agente abiertas a la vez, cada una sabe cuál
  es.** En Hermes y OpenClaw, la que abriste primero ya no se cree la
  segunda, ni ve su memoria ni guarda sus notas en ella.
- **La primera vez que abres un agente con OpenClaw ya no falla por
  tardar.** Workspace prepara su perfil en un solo paso y le da el tiempo
  que necesita; si aun así se pasa, te lo dice en una línea y basta con
  volver a abrirlo.
- **OpenClaw ya no aprende skills por su cuenta.** Su «taller de skills»
  corría cada semana, sin ventana, una revisión por agente y guardaba lo
  aprendido fuera de tu cerebro; Workspace lo apaga. Pedirle que cree una
  skill sigue funcionando.
- **OpenClaw recupera antes la conversación que cerraste con la X**: al
  cerrar normal otra pestaña, Workspace la guarda. Mientras guarda al salir
  de OpenClaw ves «Guardando…» al centro, en vez de una ventana quieta.
- **OpenClaw sabe quién eres y, en Windows, que su terminal es PowerShell.**
  El bloque de la pestaña nombra al socio activo y le recuerda separar
  comandos con `;`.
- **Cuando Workspace usa OpenClaw sin ventana** (por ejemplo, al personalizar
  un agente), cada pedido va en su propia conversación y ya no se mezcla con
  la principal de tu agente; cada una empieza diciéndole quién es, así que
  contesta con el nombre de tu agente.
- **En Windows, cuando Workspace usa OpenClaw u OpenCode sin ventana, el
  motor recibe tu pedido completo.** Antes le llegaba solo la primera línea (al
  personalizar un agente, sin las reglas ni lo que escribiste en el
  formulario), y unas comillas en ese texto podían hacer que Windows
  ejecutara parte de él como un comando.
- **Si el respaldo de OpenClaw falla al salir, el aviso se queda a la vista
  y Workspace lo vuelve a intentar** la próxima vez que abres el agente.
  Antes, al quitar «Guardando…» se borraban el aviso y lo que había en la
  terminal, y el respaldo no se reintentaba.
- **Tu agente se presenta con el nombre que dice su identidad.** Cuando
  Workspace usa OpenClaw sin ventana, el agente contesta con el nombre de su
  `BRAIN.md` («# Soy Ventisca») aunque su carpeta se llame de otra forma, y
  un agente que cargas desde su carpeta toma ese nombre. Los agentes que ya
  tienes conservan el suyo.

## 0.5.0 — 2026-10-21

**Novedades**
- **«Cargando…» al abrir un agente.** Mientras Workspace lo prepara, antes del
  menú de pestañas, ves «Cargando…» al centro de la pantalla con el nombre del
  agente, en vez de una pantalla quieta. En Hermes y OpenClaw también sale al
  elegir la pestaña, mientras se prepara y, en OpenClaw, mientras arranca su
  gateway. No tapa ningún aviso: si Workspace tiene algo que decirte, sale
  debajo.
- **El mapa de la memoria**, en la portada del hub: la fila «Mapa de la
  memoria», justo debajo de tus agentes, lo abre con el agente que tenías
  apuntado (Esc te regresa al hub). También está en Documentación (el primer
  renglón, o la tecla `m`). Es el árbol real del cerebro del agente elegido,
  como en «Agregar agente», con lo que vive fuera de él (esta PC y la
  conversación de su motor). Cada pestaña (todo el recorrido, abrir, trabajar,
  cerrar, retomar, cada persona, los motores y lo que aprende) ilumina los
  archivos que toca, en orden y en colores: lo que se lee, lo que se escribe y
  lo que es de cada persona, con tu usuario, tu pestaña y la sesión de su
  motor reales. ← → o los números cambian de paso; ↑↓ desplaza si no cabe; Tab
  cambia de agente; Enter abre lo que lo demuestra.
- **Hermes y OpenClaw usan la misma memoria y las mismas skills que los demás
  motores.** Su memoria de fábrica sigue apagada (así ningún agente lee las
  conversaciones de otro); lo que cambia es que ahora reciben bien la de tu
  cerebro:
  - **Hermes, al retomar una pestaña**, recibe con tu primer mensaje la memoria
    de la pestaña al día, con lo que anotaste en otro motor, y otra vez si
    alguien más la cambia mientras está abierta. Antes seguía con la que tenía
    cuando abriste la conversación. Usa el mismo hook del tono, así que
    necesita que lo hayas aprobado.
  - **Hermes usa las skills de tu cerebro** y ya no crea skills en su perfil,
    que comparten todos tus agentes (las de uno aparecían en los demás).
  - **OpenClaw lee la memoria larga de tu cerebro** (`STATE/MEMORY.md`) en cada
    mensaje, con su hook oficial. Su búsqueda por significado sigue apagada:
    para indexar tu cerebro mandaría tus notas a un servicio externo.
  - **Lo que Workspace le pide a OpenClaw sin abrir ventana** (por ejemplo,
    personalizar un agente) lo contesta tu agente, no el agente de fábrica de
    OpenClaw.

**Menos cosas a la vista (se quitan en la 0.6)**
- **Workflows** (`workspace wf`), la app **Proyectos** (`workspace proyectos`)
  y la **terminal partida** (`workspace split`) ya no aparecen en la ayuda, en
  la pantalla Comandos, en el manual ni en Documentación. Si escribes el
  comando, sigue funcionando como antes.
- La terminal partida ya no se abre desde el hub aunque la tuvieras
  encendida: tu agente abre en la ventana normal, con las mismas pestañas y
  conversaciones. Sus ajustes salen de Personalización.
- En la 0.6 se quita su código: Proyectos y la terminal partida desaparecen,
  y Workflows queda solo para quien desarrolla Workspace. Tus datos se
  quedan: tus proyectos (`~/.claude/workspace/proyectos/`), las corridas de
  tus flujos (`~/.claude/workspace/workflows/`) y tus ajustes siguen en tu
  máquina; nada se borra.

**Arreglos**
- Documentación ya no dice que solo Claude Code recibe tu tono en cada mensaje
  (Hermes también) ni que la maleta guarda los archivos tocados en todos los
  motores (solo en Claude Code y Codex).
- `workspace doctor` ya no dice que un `MEMORY.md` (o una carpeta `memory/`)
  suelto en la raíz del cerebro «no afecta» cuando el agente usa OpenClaw:
  OpenClaw lo lee en cada mensaje como si fuera la memoria del agente. Te
  ofrece apartarlo a `motores/openclaw/` (`workspace migrate --offer …`, o «no
  gracias» con `--decline`); nunca borra nada.
- El manual ya no dice que el perfil de Hermes se crea copiando tus llaves: se
  crea con tu modelo y sin tus llaves, y el proveedor se conecta una vez en
  Motores › cuenta y proveedor.
- Una regla que escribiste tú y que pide aprobación o confirmación (por
  ejemplo, «Si dudo, pregunto antes de borrar») ya no hace que tu agente
  reciba al abrir que «las aprobaciones se retiraron». Ese aviso sale solo si
  en tu cerebro queda, tal cual, una instrucción vieja de la plantilla de
  Workspace sobre aprobar skills o memoria, y le dice que tus reglas se
  respetan.
- **Ningún texto se pierde contra el fondo del tema en el chat de tus
  agentes** (había textos casi negros sobre el fondo oscuro):
  - Claude Code pinta todos sus textos con el tema del hub (los resultados de
    herramientas, «User rejected…» y los marcadores eran gris oscuro), y se
    leen también en Terminal.app.
  - Hermes, OpenClaw y Claude Code en tema automático saben si el fondo que
    pintó Workspace es oscuro o claro: con un perfil de terminal claro
    escribían en negro sobre el fondo oscuro.
  - En iTerm2 3.5 o más nueva, la Terminal de macOS 26, Windows Terminal,
    VS Code (Mac y Linux), WezTerm, Ghostty y kitty, los 16 colores de la
    terminal (los que usan Codex y los comandos) salen del tema. En las demás
    terminales no se tocan. Al cerrar el hub la terminal los recupera; si
    abriste un agente, los conserva hasta que cierres la pestaña, como ya
    pasaba con el fondo.
  - Un fondo personalizado claro con un tema oscuro (o al revés) ya no deja el
    texto ilegible: se queda el fondo del tema. Un fondo elegido aparte en un
    tema sin fondo propio ya pinta también el texto, y la luz roja en un tema
    claro deja el fondo claro, entintado de rojo.
  - `workspace doctor --bundle` incluye tu terminal y el tema que usa cada
    motor, sin ninguna llave.

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
