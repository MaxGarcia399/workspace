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

Workspace **nunca lee ni toca** las credenciales de estos programas: el login lo hace cada uno.

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

**Cambiarlo después:** en el hub, **Agentes** → elige el agente → **Enter**. Dos interruptores, por agente, que aplican desde su próxima sesión en los tres
motores:

| Interruptor | De entrada | Qué hace |
|---|---|---|
| Lee y escribe en su cerebro sin preguntar | **sí** | apagado, te pregunta antes de crear o editar cada archivo, también en su cerebro (`"ask"`) |
| Revisión de skills al cerrar la sesión | no | ver [Revisión de skills](#revisión-de-skills-opcional) |

Sin abrir el hub (o pidiéndoselo al propio agente), desde la carpeta de Workspace:
`python3 agent_admin.py prefs <agente> --autonomy brain|ask --skill-review|--no-skill-review`.

Si un agente tuyo viene de una versión anterior que le dejaba correr cualquier comando sin
preguntarte, al actualizar pasa solo a esto (su configuración anterior queda respaldada).

## Revisión de skills (opcional)

La otra elección: **«¿Revisión automática de skills al cerrar cada sesión?»**. Si dices que sí,
al cerrar cada sesión el motor del agente (Claude Code, Codex o Antigravity; si ese no está,
Claude Code) lee en segundo plano lo que pasó y mejora las skills que usó con lo que corregiste.
Las skills nuevas quedan como propuesta en `skills/_propuestas/` hasta que tú las apruebes.

- Es una segunda red: el agente ya aprende durante la conversación (crea o mejora skills y lo
  dice en el bloque del final de cada respuesta). La revisión al cerrar recoge lo que se le pasó.
- Lee una copia neutral de la sesión, solo escribe dentro de `skills/` del cerebro y no usa la
  red. En Claude Code y Antigravity tampoco usa la terminal; en Codex la usa solo para leer y
  editar esos archivos, dentro de su caja.
- No hace esperar el cierre; las sesiones muy cortas no se revisan y corre como mucho una vez
  cada dos horas por cerebro.
- **Usa un poco de tu suscripción** del motor.
- Viene apagada. Se guarda por agente (`"skill_review"` en su `agent.json`) y se prende o apaga
  en **Agentes** (elige el agente y Enter). Para los agentes que no eligieron manda el ajuste global
  `hooks.skill_review` (apagado), que se cambia desde la carpeta de Workspace con
  `python3 settings.py set hooks.skill_review on` (u `off`).

## Elegir y cambiar de motor

- **Por defecto para todos:** lo eliges en el primer arranque (`workspace onboarding`).
- **Para un agente:** en el hub, apúntalo y usa ← → para ciclar entre los motores
  instalados. Se guarda en esta máquina.
- **Estado de cada motor:** sección **Motores** del hub — si está instalado, si tiene sesión,
  qué puede hacer.

Cambiar de motor **no** cambia la identidad ni el cerebro del agente. Lo que no viaja es el
historial interno de cada proveedor: una conversación empezada en un motor no aparece en otro.

## No todos los motores pueden lo mismo

Claude Code es hoy el más integrado (memoria inyectada al arrancar, avisos en vivo, barra de
estado propia). Codex y Antigravity funcionan envueltos por Workspace, con algunas funciones
de menos. La lista exacta, por motor y por sistema: [Compatibilidad](compatibilidad.md).
