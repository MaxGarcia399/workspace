# Agentes y motores

## El agente

Un agente es una identidad con su **cerebro**: una carpeta de archivos Markdown que vive
**fuera** de la carpeta de Workspace. Por eso actualizar o reinstalar Workspace no toca a tus
agentes. Créalos o cárgalos desde el hub con **Agregar agente**; revísalos con
**Agentes**.

## El motor

El motor es el programa de IA que conversa con el modelo. Workspace **no reescribe** esa
parte: usa el programa oficial de cada proveedor, con **tu cuenta**.

| Motor | Programa | Cuenta | Cómo entras |
|---|---|---|---|
| **Claude Code** | `claude` (Anthropic) | tu suscripción | corre `claude` una vez y sigue el login |
| **Codex** | `codex` (OpenAI) | tu suscripción de ChatGPT | `codex login` |
| **Antigravity** | `agy` (Google) | tu cuenta Google | el propio `agy` te pide entrar |
| **OpenCode** | `opencode` (código abierto) | el proveedor que conectes (OpenRouter, Anthropic, OpenAI…) | `opencode auth login` |
| **OpenClaw** | `openclaw` (código abierto) | el proveedor y el modelo que elijas | Motores › **cuenta y proveedor** (`openclaw --profile workspace configure --section model`, el selector oficial de OpenClaw) |
| **Hermes** | `hermes` (Nous Research, código abierto) | el proveedor y el modelo que elijas | Motores › **cuenta y proveedor** (`hermes --profile workspace model`, el selector oficial de Hermes) |

Workspace **nunca lee ni toca** las credenciales de estos programas: el login lo hace cada uno.
Con OpenCode, OpenClaw y Hermes, el modelo lo eliges tú en su propia configuración; Workspace no lo cambia.

**Tu cuenta, tu proveedor y la configuración de cada motor son tuyos.** Workspace no tiene un
sistema de proveedores, no guarda llaves y no cambia ajustes del motor: en **Motores**, cada
motor tiene siempre la opción **cuenta y proveedor**, que abre el selector oficial de cuenta,
proveedor y modelo de ese motor (`claude auth login`, `codex login`, `agy`, `opencode auth login`,
`openclaw --profile workspace configure --section model` o `hermes --profile workspace model`). Ahí
entras, cambias de cuenta o conectas otro proveedor. El resto de la configuración del motor sigue
siendo tuya, con sus propias herramientas.

**Versiones.** Workspace usa siempre la versión más nueva de cada motor. En **Motores**, OpenCode,
OpenClaw y Hermes muestran la suya: **probada** (Workspace ya la probó), **nueva** (lo normal: cada
versión nueva se prueba sola a diario y, si algo falla, `workspace update` trae el ajuste),
**vieja** o **muy vieja** (actualízala) o **con falla** (un problema comprobado en tu sistema: Enter
te dice cuál y qué hacer, y aun así puedes abrir el agente). Claude Code, Codex y Antigravity no
dependen de la versión.

Lo único que Workspace mantiene es lo que necesita de tu **cerebro** para funcionar. Con OpenClaw:
que no cree archivos propios en tu cerebro, que el workspace de tu agente sea tu cerebro y que lea
la memoria de tu cerebro. Con Hermes: que no le ponga su propia identidad ni su propia memoria
encima de la de tu agente, y que use y guarde sus skills en tu cerebro. Lo revisa cada vez que
abres el agente; si lo cambiaste desde el setup, lo regresa y te avisa en una línea.

OpenClaw corre con un **perfil propio de Workspace** (aparte del OpenClaw que uses por tu
cuenta) que trabaja sobre tu mismo cerebro sin crear archivos extra. Conectas el proveedor una
vez y sirve para todos tus agentes. Puedes tener **varios agentes de OpenClaw abiertos a la
vez**: al abrir el primero, Workspace enciende en segundo plano el servicio de OpenClaw (tarda
unos segundos) y lo apaga solo cuando cierras el último. En cada mensaje lee la **memoria larga
de tu cerebro** (`STATE/MEMORY.md`, la misma de los demás motores) con su hook oficial. De su
memoria propia, Workspace solo apaga lo que escribiría en tu cerebro: su búsqueda de memoria
sigue encendida, pero solo busca en los archivos de memoria propios de OpenClaw, que tu cerebro
no usa, y sin un servicio de embeddings busca por palabras (si el agente dice que está
«degradada», es por eso y es normal). Workspace no la apunta a tu cerebro, porque para indexarlo
mandaría tus notas a un servicio externo. Cuando Workspace le pide algo sin abrir ventana (por
ejemplo, personalizar un agente), contesta tu agente, no el agente de fábrica de OpenClaw. Si tu
cerebro tiene de antes un `MEMORY.md` o una carpeta `memory/` sueltos en la raíz, OpenClaw los lee
en cada mensaje como si fueran la memoria de tu agente: `workspace doctor` te lo dice y te ofrece
apartarlos a `motores/openclaw/` (no borra nada).

Hermes también corre con un **perfil propio de Workspace** (`workspace`, en
`~/.hermes/profiles/workspace`): **tu Hermes personal no cambia** (ni su configuración, ni su
identidad, ni su memoria, ni su historial). La primera vez que abres un agente con Hermes,
Workspace crea ese perfil con tu modelo pero **sin copiar tus llaves**: conecta tu proveedor una
vez en Motores › **cuenta y proveedor**. **El proveedor y el modelo se cambian desde Motores**
(cuenta y proveedor abre el selector oficial de Hermes dentro de ese perfil). Lo que conviene
saber:

- **La identidad es la de tu agente.** Hermes trae una propia («Hermes Agent», de Nous Research);
  en el perfil de Workspace queda neutral y la identidad llega por el `AGENTS.md` del cerebro, que
  para Hermes lleva además una **copia del núcleo de tu agente** (`BRAIN.md`, `BOOT/` y tu perfil
  de socio): así se presenta con su carácter aunque el modelo no lea archivos por su cuenta. La
  copia se rehace en cada arranque; lo que editas sigue siendo el cerebro. Una pestaña que ya
  tenía conversación conserva la identidad con la que empezó (Hermes la guarda); para ver un
  cambio de identidad, abre una pestaña nueva.
- **La memoria de Hermes está apagada en ese perfil**, y también su búsqueda de conversaciones
  pasadas (en la terminal y en un bot de Discord conectado a ese perfil): el perfil lo comparten
  todos tus agentes y uno podía leer las conversaciones de otro.
  La memoria y la historia de cada agente viven en su cerebro. Al empezar o **retomar** una
  conversación, Hermes recibe con tu primer mensaje la **memoria larga de tu cerebro**
  (`STATE/MEMORY.md`, hasta 20 000 caracteres: si es más larga, el principio y dónde está el
  resto) y la memoria de la pestaña al día (lo que anotaste en otro motor incluido), y esta
  otra vez si alguien más la cambia mientras está abierta; lo que anota él mismo no se le repite.
- **Usa las skills de tu cerebro** (`skills/`) además de las suyas de fábrica, y **guarda en tu
  cerebro las que aprende**. Cuando crea una skill (por su cuenta durante la conversación o porque
  se lo pides con `/learn`), queda en `skills/aprendidas/` del cerebro del agente de esa pestaña;
  cuando mejora una que ya existe, la cambia ahí mismo. Nada queda en el perfil que comparten tus
  agentes: lo que aprende uno no lo ve otro. Al cerrar cada sesión, Workspace anota las nuevas en
  el catálogo del cerebro (`skills/README.md`), así que **tus otros motores también las ven y las
  usan**. Su repaso automático de skills (el que corre solo al terminar una tarea larga) está
  apagado. Con un Hermes anterior a la 0.21.6 las sigue guardando en su perfil: actualízalo. Si una
  skill de tu cerebro se llama igual que una de fábrica, gana la de fábrica. Sus tareas
  programadas siguen como en tu Hermes.
- **Tu tono llega en cada mensaje**, con un hook de Workspace que lo añade (y que lleva tu memoria
  y anota qué pestaña es dueña de cada conversación). Si es el único hook
  del perfil, Hermes lo aprueba solo al abrir. Si agregaste hooks tuyos a ese perfil, Workspace no
  aprueba nada por ti: Hermes te pregunta si apruebas el de Workspace; responde «y». Si dices que
  no, el tono y la memoria larga solo llegan al abrir y una pestaña retomada no recibe la memoria
  nueva.
- **Hermes no permite mandarle un mensaje de arranque.** En una pestaña nueva, el agente lee su
  cerebro cuando le escribes el primer mensaje.
- Si abres dos pestañas nuevas del mismo agente a la vez y no aprobaste el hook, Workspace no
  adivina de cuál es cada conversación: no ata ninguna (la recuperas desde el historial de Hermes).

## Permisos

Al crear o cargar un agente eliges si **lee y escribe en su cerebro sin preguntarte**: viene
encendido, porque es su trabajo principal. La elección se guarda con el agente (`"autonomy"` en
su `.workspace/agent.json`, viaja con el cerebro) y cada motor la aplica a su manera.

| | Dentro de su cerebro | Terminal, archivos de fuera, red |
|---|---|---|
| **Encendido** (de entrada) | lee, crea y edita sin preguntarte | te pregunta antes |
| **Apagado** | te pregunta antes de crear o editar | te pregunta antes |

En Codex, con el acceso encendido, los comandos corren sin preguntar **dentro de su caja**, que solo le deja escribir en su
cerebro y en las carpetas temporales del sistema, sin red; lo que necesite salir de ahí te lo pide.

Con Claude Code queda en `.claude/settings.local.json` del cerebro: reglas que le permiten leer y
editar su carpeta, y nada más. Ninguna opción desactiva las protecciones del motor. Tus reglas propias en ese archivo se
respetan.

Con OpenCode, OpenClaw y Hermes, Workspace **todavía no aplica** este interruptor: cada uno pregunta según
sus propios permisos (su configuración).

**Cambiarlo después:** en el hub, **Agentes** → elige el agente → **Enter**. Dos interruptores, por agente, que aplican desde su próxima sesión en
Claude Code, Codex y Antigravity:

| Interruptor | De entrada | Qué hace |
|---|---|---|
| Lee y escribe en su cerebro sin preguntar | **sí** | apagado, te pregunta antes de crear o editar cada archivo, también en su cerebro (`"ask"`) |
| Revisión de skills al cerrar la sesión | no | ver [Revisión de skills](#revisión-de-skills-opcional) |

Sin abrir el hub (o pidiéndoselo al propio agente), desde la carpeta de Workspace:
`python3 agent_admin.py prefs <agente> --autonomy brain|ask --skill-review|--no-skill-review`.

Si un agente tuyo viene de una versión anterior que le dejaba correr cualquier comando sin
preguntarte, al actualizar pasa solo a esto (su configuración anterior queda respaldada).

## Revisión de skills (opcional)

La otra elección: **«¿Revisión automática de skills?»**. Si dices que sí, al cerrar cada sesión
Workspace guarda una vista de lo que pasó y, **al abrir la siguiente**, tu agente la revisa en
esa misma sesión, a la vista, y mejora las skills que usó con lo que corregiste. Las skills
nuevas se crean directo en su categoría, como ya hace durante la conversación. Lo reporta en una
línea del bloque del final de su respuesta.

- Es una segunda red: el agente ya aprende durante la conversación (crea o mejora skills y lo
  dice en el bloque del final de cada respuesta). La revisión recoge lo que se le pasó.
- **Nada corre sin ventana ni a escondidas:** no se lanza ningún proceso al cerrar; la revisión
  la hace tu agente cuando lo abres, frente a ti.
- Lee una copia neutral de la sesión que se guarda dentro de tu cerebro, en
  `.claude/skill-review/` (carpeta oculta: no se sincroniza ni entra a git), y solo escribe
  dentro de `skills/`.
- Las sesiones muy cortas no se revisan y se pide como mucho una vez cada dos horas por cerebro.
- **Usa un poco de tu suscripción** del motor, en esa sesión.
- Viene apagada. Se guarda por agente (`"skill_review"` en su `agent.json`) y se prende o apaga
  en **Agentes** (elige el agente y Enter). Para los agentes que no eligieron manda el ajuste global
  `hooks.skill_review` (apagado), que se cambia desde la carpeta de Workspace con
  `python3 settings.py set hooks.skill_review on` (u `off`).

## Elegir y cambiar de motor

- **Por defecto para todos:** lo eliges en el primer arranque (`workspace onboarding`).
- **Para un agente:** en el hub, apúntalo y usa ← → para ciclar entre los motores
  instalados. Se guarda en esta máquina.
- **Estado de cada motor:** sección **Motores** del hub — si está instalado, si tiene sesión,
  qué puede hacer, y **cuenta y proveedor** para abrir su configuración oficial.

Cambiar de motor **no** cambia la identidad ni el cerebro del agente. La conversación en sí
es de cada proveedor (una empezada en un motor no aparece en otro), pero **la pestaña sí
viaja**: su memoria es de Workspace y es la misma en los seis motores.

## La memoria de cada pestaña

Funciona igual en todos los motores y no tienes que hacer nada:

- **Mientras trabajas**, el agente guarda lo importante en el momento, con una etiqueta:
  decisión, pendiente, hecho, nota, dato o preferencia (`workspace memoria nota`). Los pendientes
  llevan un número (P-3) y se cierran cuando quedan hechos.
- **Al cerrar**, Workspace (sin IA) arma la **maleta** de la pestaña: lo último que pediste, la
  última respuesta y los archivos que tocó. Ordena el diario, archiva lo viejo y sube tus datos y
  preferencias a la memoria del agente. También si cerraste la ventana con la X.
- **Al abrir** la pestaña, en ese u otro motor, el agente recibe un solo paquete: el resumen, lo
  que sigue abierto, las notas nuevas y la maleta si vienes de otro motor. Si toca, actualiza su
  resumen a la vista, en una respuesta corta.

Todo vive en el cerebro (`STATE/sessions/<socio>/`), así que también viaja a tus otras máquinas.
Nada corre de noche ni sin ventana. Claude Code guarda además su memoria propia dentro del
cerebro, una carpeta por persona (`motores/claude-code/memoria/<socio>/`): en un cerebro
compartido, el de cada quien carga solo la suya. Se apaga en Ajustes si prefieres dejarla en la
máquina.
Para verla: `workspace memoria ver` (con la pestaña activa).

## No todos los motores pueden lo mismo

La memoria de cada pestaña es la misma en todos. Claude Code es hoy el más integrado (avisos en
vivo, barra de estado propia, su memoria propia en el cerebro). Codex, Antigravity, OpenCode, OpenClaw y Hermes funcionan envueltos por Workspace, con algunas
funciones de menos. La lista exacta, por motor y por sistema: [Compatibilidad](compatibilidad.md).
