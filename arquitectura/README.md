# Arquitectura nueva · F0: contrato y probador

Workspace pasa a ser un paquete de extensiones oficiales por motor (plugin, hooks,
skills y MCP) conectado a un núcleo. F0 deja el contrato y las herramientas para
construirlo, **sin tocar todavía el sistema viejo**: nada de esta carpeta se
instala ni se llama desde el harness de hoy.

| Pieza | Archivo | Cómo se revisa |
|---|---|---|
| Contrato de los 8 momentos del hook | `momentos.json` (+ la tabla en `engines/EVENTS.md`) | `python3 -m arquitectura.contrato` |
| Lista del MCP núcleo | `mcp_nucleo.json` | ídem |
| Ficha de cada motor | `fichas/<motor>.json`, contra `ficha.esquema.json` | ídem |
| Paquete fuente | `paquete/` | `python3 -m arquitectura.generar <destino>` |
| Probador de caja negra | `probador.py`, `preguntas.json`, `sonda_hook.py` | `python3 -m arquitectura.probador` |

Pruebas: `tests/test_arq_f0.py` (el probador, con el motor falso de `tests/fixtures/arq/`).

## 1 · Los 8 momentos

Nombres neutrales sobre el vocabulario N9 (`engines/EVENTS.md`). Lo que entra es lo que
el traductor de cada motor (F1) le garantiza al núcleo, además de los campos comunes
`engine`, `session_id`, `cwd` y `ts`. Lo que devuelve es lo único que el núcleo puede contestar.

| Momento | N9 de hoy | Entra | Devuelve | Qué hace Workspace |
|---|---|---|---|---|
| `session_start` | `session_start` | `source` (startup, resume, compact, clear) | `context`, `visible` | Guarda el número de la conversación y entrega el paquete de la pestaña. |
| `user_prompt` | `user_prompt` | `prompt` | `context`, `block`, `reason` | Marca «pensando», guarda tu mensaje y entrega las notas pendientes. |
| `pre_tool` | `pre_tool` | `tool_name`, `tool_input` | `decision`, `reason` | Marca «usando X» y bloquea lo prohibido. |
| `post_tool` | `post_tool` | `tool_name`, `ok`, `files` | `context` | Anota los archivos tocados (y las notas, donde el mensaje no inyecta). |
| `permission_request` | — (nuevo) | `tool_name`, `tool_input` | `decision`, `reason` | Marca «esperando tu permiso»; no decide por el socio. |
| `turn_end` | `turn_end` | `last_assistant_message`, `stop_hook_active` | `follow_up` | Marca «listo», arma la maleta y da el «sigue» (tope de 3). |
| `compact` | `pre_compact` | `phase` (before, after), `trigger` | `context` | Antes guarda la maleta; después reentrega la identidad. |
| `session_end` | `session_end` | `reason` | — | Marca «cerrado» y cierra la maleta y las métricas. |

Qué evento oficial de cada motor cae en cada momento: la tabla de `engines/EVENTS.md`,
generada de las fichas.

## 2 · El MCP núcleo

9 herramientas (`mcp_nucleo.json`, versión 2 de F6), sin salas ni decisores:
`memoria_nota`, `memoria_checkpoint`, `memoria_ver`, `pendientes`, `skills_lista`,
`skill_leer`, `tarea_actual`, `preguntar` y `reportar_avance`. Cada una trae su entrada
(JSON Schema cerrado), su salida, sus errores (`SIN_PESTANA`, `ENTRADA_INVALIDA`,
`CONFLICTO`, `NO_ENCONTRADO`, `NO_DISPONIBLE`), qué usa debajo y qué reemplaza de hoy.
Ninguna recibe cerebro, pestaña ni motor: escriben solo en la pestaña de la ventana que
abrió al motor. Las sirve `nucleo_mcp.py` (sección 7).

## 3 · El paquete: una fuente, cuatro formatos

```
paquete/                         LA fuente
  workspace.json                 nombre, descripción, servidor MCP y lanzadores
  skills/workspace/SKILL.md      la skill «workspace»
  lanzador/hook.py               el lanzador FIJO de los hooks: <destino> <momento>
  lanzador/mcp.py                abre el MCP (F0: memoria_mcp.py de hoy)
  lanzador/comun.py              encuentra el Workspace instalado
```

`python3 -m arquitectura.generar <destino>` arma:

- `claude/`: plugin de Claude Code (`.claude-plugin/plugin.json`, `hooks/hooks.json`,
  `.mcp.json`, `skills/`). Lo cargan Claude Code, Copilot, OpenClaw y Antigravity. Con
  `antigravity/`: los hooks de Antigravity en SU forma (hooks5: la de Claude, agy la salta).
- `agent-plugins/`: Agent Plugins 1.0 (`plugin.json`, `mcp.json`, `skills/`) y los hooks
  de Codex, Cursor, Kiro (perfil del agente) y Hermes (YAML del perfil), cada uno en la
  ruta y el dialecto de su ficha.
- `opencode/`: plugin JS de OpenCode (`package.json`, `index.js`).
- `openclaw/`: plugin NATIVO de OpenClaw (`openclaw.plugin.json` con el servidor MCP y las skills, `package.json`,
  `index.js` con sus avisos tipados `api.on`). Va en la carpeta de plugins del workspace de su agente
  (`<cerebro>/.openclaw/extensions/workspace`) y se enciende en el perfil propio de Workspace. El gateway lo carga para
  TODOS los agentes del perfil: no lleva las skills del cerebro (llegan por el `skills/` del workspace), y sus avisos y
  su MCP hallan la pestaña por la clave de la sesión (el índice número → pestaña; el aviso `before_tool_call` le suma
  la clave a cada herramienta del MCP, que el gateway abre sin decirle de qué sesión es).

Los hooks de los 3 formatos llaman al mismo comando: `python3 "<raíz>/lanzador/hook.py"
<destino> <momento>`. La raíz es la variable que da el motor (`${CLAUDE_PLUGIN_ROOT}`,
`${CURSOR_PLUGIN_ROOT}`) o `{{RAIZ}}`, que se fija al instalar. El hook neutral de hoy
está enchufado en el destino `claude`: el lanzador le pasa el evento N9 a
`workspace_hook.py`. Los otros destinos no hacen nada hasta que F1 traiga su traductor.

Los hooks que van en el proyecto (hooks5: el `.codex/hooks.json` y el `.agents/hooks.json`
del cerebro) llaman al lanzador en una carpeta FIJA del estado de Workspace
(`sesion.lanzador_fijo`): Codex guarda la confianza de sus hooks por huella, y así la que
el socio da una vez en `/hooks` sigue valiendo al actualizar.

## 4 · La ficha de cada motor

`fichas/<motor>.json`: vía de control y semáforo, los 8 momentos (eventos oficiales,
estado y qué puede cada uno), cómo carga el paquete por sesión, permisos por sesión, uso
del plan, número de conversación, tono y cómo lo corre el probador. Todo sale de la
documentación oficial; `probador.verificado` dice si ya pasó por el probador.

## 5 · El probador de caja negra

```
python3 -m arquitectura.probador                    los 9
python3 -m arquitectura.probador --motor codex      uno
  --home-aislado DIR   HOME por motor en DIR/<motor>, para iniciar sesión ahí una vez a mano
  --salida DIR         dónde deja informe.md, informe.json y, por motor, registro y salida
python3 -m arquitectura.probador --login codex --home-aislado DIR
                       abre el motor con su pantalla en ese HOME, para su login oficial
python3 -m arquitectura.probador --home-real --salida DIR
                       el HOME de verdad (las sesiones ya iniciadas) con un proyecto temporal
```

**`--home-real`** va con la vía SOLO por sesión de cada ficha (`probador.real`: flags,
`--plugin-dir`, archivos en la carpeta del proyecto). Un motor sin ella (hoy OpenClaw y
Hermes) no se corre. En este modo se rechaza todo paso que escriba fuera del proyecto o
que corra un instalador. Red de seguridad: antes y después de cada motor, la huella
(tamaño + sha256) de su config global (`config_global` de la ficha; de un JSON que el motor
reescribe solo, solo las claves de config). Si algo cambió, el informe dice **FALLA** con
el archivo y el probador sale con 1. Solo se guardan huellas, nunca el contenido. Ojo: si
el socio cambia esa config a mano durante la corrida, también sale FALLA.

Por motor arma el paquete en una carpeta temporal, pone la sonda en el lugar del
lanzador (mismo comando), corre el binario oficial con su ficha en un cerebro de prueba,
con HOME y config temporales, y responde `preguntas.json` (la lista 11.2 del plan): con lo
que anotó la sonda, con la salida del motor, con su `--help` o, si no se puede sin
pantalla, con una instrucción para hacerlo a mano. Nunca lee el código de un motor, nunca
escribe fuera de su carpeta y no le pasa al motor el entorno del usuario.

**Se corre fuera de un sandbox** (los motores necesitan red y su login).

## 6 · F1: el paquete por sesión, el registro de eventos y el número oficial

**Encendido de fábrica** (el sistema nuevo, también para quien actualiza: migración
`202611182300_sistema_nuevo`, con su aviso de una línea y su deshacer). Se apaga con el ajuste
`arquitectura.paquete` o, para una corrida, con `WORKSPACE_PAQUETE=0` (`1` lo enciende). Quien lo
apagó a mano queda apagado. `workspace doctor` revisa, por motor instalado, el MCP, los hooks y las
skills (sección 10).

- **`sesion.py`:** los dos caminos de arranque de hoy lo llaman justo antes de abrir el motor
  (`engines/claude_code.launch` e `interactive.run_official_cli_interactive`). Hace tres cosas:
  1. Instala el paquete en el estado de esta máquina, una carpeta por versión.
  2. Lo carga por la vía por sesión de la ficha (`sesion`). Hoy son Claude Code, Copilot y Cursor
     con `--plugin-dir`, OpenCode con su plugin en `.opencode/plugins/` del cerebro, sin rutas de
     la máquina, y OpenClaw con su plugin nativo en `.openclaw/extensions/` del cerebro (el workspace de su
     agente). Hermes (cable-hermes), que guarda todo en la config de un perfil, con un perfil PROPIO por
     agente (`workspace-<agente>`, ficha · `sesion.perfil_agente` y `sesion.preparar` →
     `engines/hermes.sesion_perfil`). Los demás dicen en su ficha por qué todavía no.
  3. Fija el número oficial de la conversación (D3-a) y lo guarda en la pestaña, junto al atado de
     hoy. Si algo falla, el motor abre como hoy.
- **`registro.py`:** el registro de eventos de cada pestaña.
  - Es solo de anexar, en el estado de la máquina; no viaja con el cerebro.
  - El hook del paquete anota ahí cada momento.
  - `estado()` da `abierto`, `pensando`, `usando`, `esperando_permiso`, `listo` o `cerrado`.
- **El lanzador del paquete:**
  - Traduce el JSON de cada motor (`lanzador/traductor.py`) y lo anota en la pestaña.
  - Halla la pestaña por las variables de Workspace o, si el motor no las hereda, por el número
    de conversación.
  - Corre el hook de hoy solo si el cerebro ya no lo cablea por su cuenta
    (`WORKSPACE_PAQUETE_HOOKS=1`). Así nada se dispara dos veces.
- **La página:**
  - Con el paquete encendido, `front_vivo` toma el estado de la pestaña de la página del registro.
    No lee su pantalla; de herdr solo mira si el panel sigue ahí.
  - `/api/front/eventos?agente=&desde=` da los eventos nuevos y el estado.

## 7 · F6: el MCP núcleo, el paquete al abrir y el tono en el sistema

Con el paquete encendido (sección 6), y sin decisores ni salas.

- **`nucleo_mcp.py`:** el servidor `workspace` que abre `lanzador/mcp.py`. Valida con el
  contrato y, debajo, usa lo mismo que el comando de hoy, para que no haya dos dueños:
  - `memoria_mcp` y `memoria.py`, que es lo que corre `workspace memoria nota|checkpoint|ver`;
  - lo vigente de la ficha y `STATE/PENDIENTES.md`;
  - `skills/` del cerebro;
  - el registro de eventos, para `tarea_actual` y `preguntar`;
  - `pasos.aplicar`, para `reportar_avance`.

  `preguntar` usa el formulario oficial (MCP elicitation) si el cliente lo ofrece. Si no,
  devuelve `en_chat` y la pregunta queda en el registro, donde la página la enseña como un
  permiso.
- **`nucleo.py`:** el bloque `nucleo` de cada ficha.
  - `mcp`: el servidor declarado y preaprobado por sesión (argumentos, entorno o archivos
    del proyecto).
  - `al_abrir`: el paquete de la pestaña por el hook de inicio (`lanzador/hook.py`, en la
    forma de cada dialecto) o por las instrucciones del MCP.
  - `tono`: la pieza de sistema. Es un argumento, una regla del proyecto, las
    instrucciones del MCP o el hook de inicio.

  `sesion.para_lanzar` lo aplica y deja en el entorno `WORKSPACE_NUCLEO_AL_ABRIR` y
  `WORKSPACE_TONO_SISTEMA`. Con eso el camino de hoy no lo repite: el paquete en el hook
  neutral y en el bloque de la pestaña, y el tono por mensaje.
- **La página:**
  - Sus corridas por la capa de control traen el núcleo (`pagina_v2.nucleo_para`). Sus
    hooks van marcados `WORKSPACE_VIA=pagina`, así que no cuentan como su terminal.
  - La pregunta de una skill es una tarjeta, y su respuesta va por la capa de control.
  - «Hacer ahora» manda la revisión de skills por la misma vía
    (`skill_review.hacer_ahora_por_control`).

## 8 · F7: skills nativas, permisos por sesión y lo prohibido

- **Las skills del cerebro en el menú `/`** (`skills_cerebro.py`): salen del catálogo del cerebro
  (`skill_meta.scan_catalog`: vivas y disponibles en esta máquina) y van en el paquete de ESE cerebro
  (`sesion.instalar(cerebro)`, con la huella de sus skills) como vista plana `skills/<nombre>/`:
  nombre en kebab-case igual a su carpeta, su descripción y el sello `.workspace-skill.json`.
  - Por el plugin: Claude Code (`/workspace:<skill>`), Copilot y Cursor; Kiro por los `skill://` de su perfil.
  - En la carpeta del proyecto (`sesion.skills` · `proyecto`): OpenCode, en `.opencode/skills`. Solo se
    rehacen o quitan las carpetas con el sello; una del socio con el mismo nombre gana.
  - Un cerebro sin skills usa el paquete de todos; la poda es por cerebro (nunca le quita el paquete a otro).
- **Permisos por sesión** (`permisos.py`): la autonomía del agente es un nivel: «ask» = preguntar,
  «brain» = editar sin preguntar, «sandbox» = sin permisos SOLO dentro del sandbox del motor (si no lo
  tiene, o no en este sistema, editar). Cada ficha lo dice en `permisos.niveles` (argumentos, ajustes
  que se juntan con el `--settings` del lanzador, o el JSON de la corrida). Lo que el lanzador de hoy ya
  pone para un nivel se deja. Nunca bypassPermissions, `--dangerously-*`, el modo auto ni un «aprobar
  todo» (la guarda `permisos.revisar` y su prueba sobre las 9 fichas).
- **Lo prohibido en el hook de los 9** (`paquete/lanzador/prohibidos.py`): antes de cada herramienta,
  leer un `.env`, `*.key`/`*.pem`, una llave SSH privada, credenciales, la bóveda de Workspace o el
  llavero se niega: sale con 2 y el motivo, más el JSON de su dialecto; en OpenCode su plugin corta la
  herramienta. Corre aunque falte el harness.
- **Lo prohibido donde el aviso no corre** (`secretos.py`, cierre de la auditoría del 19-nov): por la página Codex
  (app-server), Cursor y Kiro (ACP) no corren avisos. Ahí va por lo oficial de cada motor, en lo de Workspace y nunca
  en su config global, con la misma lista: Codex, un perfil de permisos SOLO del hilo (`default_permissions` +
  `[permissions.workspace-pagina]` con `deny`; su app-server lo confirma en `activePermissionProfile`); Cursor, reglas
  `Read(…)` en el `.cursor/cli.json` de su carpeta; Kiro, su agente `workspace-pagina` (reglas `fs_read` deny) elegido
  con `_meta.kiro.modeId`. Y la capa de control (`control/base`) niega sola un permiso que pide leer lo prohibido. La
  auditoría lo prueba con un canario en un segundo turno: si sale, ✗.
- **El modo del lanzador** (ficha · `permisos.niveles.<nivel>.bandera`): donde el lanzador pone el nivel (Claude Code
  `--permission-mode auto`, Cursor `--auto-review`, Antigravity `--mode auto`), la sesión comprueba que esté y lo dice
  (`aplicado`, `por: lanzador`); `no_se_usa` = el motor no tiene ese nivel en ese camino (Copilot en su terminal, con
  la prueba en vivo de `engines/copilot.juez_en_interactivo`).
- **El reporte de la config global** (`reporte_global.py`): solo lee y lista lo que Workspace dejó fuera
  de los cerebros (sus marcas, `uninstall.plan_clean_all`) y la huella de la config global de cada ficha.
  La limpieza se decide aparte.

## 9 · F5: el número oficial, y la maleta y las métricas desde los eventos

- **Reabrir por el número oficial** (D3-a): `registro.numero_de(cerebro, pestaña, motor)` es lo último que el
  motor dijo en sus hooks (también tras un `/clear` o un fork) o, si nunca dijo uno, lo último que se le pasó al
  abrir; la página no cuenta. `sesion.para_lanzar` reabre con ese número (ficha · `sesion.id.retoma`, o `crea`
  la primera vez). Si el lanzador ya trae ese mismo número, su argv se deja; si trae otro, se cambia solo
  cuando el motor ya confirmó el oficial. `sessions_registry.resume_id` da el oficial y `bind` no ata otro: la
  adivinanza tras cerrar queda apagada. Cada cambio deja su línea en `logs/numero-oficial.log`.
- **La maleta sin IA** (`maleta.py`): lo último que pediste, lo último que respondió, las herramientas de la
  sesión y los pendientes abiertos, desde el registro (nunca un transcript), en el formato de siempre. Se
  escribe en el `session_end` del hook del paquete y se rehace al reabrir la pestaña (la sesión cortada sin
  cerrar). Donde la escribe el núcleo, la del transcript (`memoria.actualizar_maleta`) calla. Donde sus avisos no dan
  tu mensaje o su respuesta (ficha · `sesion.maleta_del_transcript`: Copilot, Cursor), sigue la del transcript, como
  con solo sus hooks (`maleta.maleta_de_hoy`).
- **Las métricas desde los eventos** (`metricas_eventos.py`): sesiones, turnos, herramientas, duración y
  errores por agente y motor; el uso oficial donde la capa de control lo da. Lado a lado con las de hoy
  (`--comparar`); `metricas_motores/` y la lectura de transcripts se retiran cuando los 9 anoten el registro.

## 10 · El sistema nuevo de fábrica, el doctor y la auditoría

- **De fábrica** (`settings.py`, `sistema_nuevo.py`): `arquitectura.paquete` viene en ON. Quien actualiza queda en el
  sistema nuevo sin hacer nada; la migración `202611182300_sistema_nuevo` solo deja el aviso de una línea al abrir un
  agente, con cómo apagarlo. Encender y apagar es un solo comando: `workspace sistema-nuevo [on | off]` (sin nada, dice
  cómo está); `workspace migrate --undo 202611182300_sistema_nuevo` también lo apaga. Quien lo apagó a mano, no recibe
  nada.
- **Conexiones y el doctor = ¿el backend está cableado como lo planeamos?** (`verificacion.py`): arriba las piezas
  comunes (el servidor local vivo y único, el registro escribiendo, el MCP núcleo respondiendo, el paquete encendido, la
  cola y el Vigía) y debajo una matriz pieza × motor con las piezas del plan (la vía de control con su nombre real
  —`claude -p --resume`, ACP, app-server, serve—, paquete, avisos, MCP con sus herramientas, formularios e
  instrucciones, skills, permisos, número oficial, maleta, misma conversación y bloqueo de lo prohibido). Cada celda:
  ✓ verificado de verdad (con fecha), ✗ falló (qué y qué hacer), «no se usa en este motor» (neutro: sin vía oficial o el
  plan no lo pide), «falta tu confianza una vez» o «sin verificar todavía». Solo cuenta la evidencia de la última
  auditoría: nada sale ✓ por tener el archivo puesto. Lo lee `GET /api/v2/conexiones` (la sección Conexiones) y la fase
  «5e · Cableado del sistema nuevo» del doctor; «Verificar ahora» (`POST /api/v2/verificar`, `verificacion.lanzar`)
  corre la auditoría en segundo plano, una a la vez, con su avance.
- **El diagnóstico del MCP núcleo** (`salud.diagnostico`, `<estado>/arquitectura/mcp-diagnostico.jsonl`): un renglón
  por arranque (qué cliente lo abrió, su versión, si ofrece formularios) y por llamada (qué herramienta y cómo salió:
  `ok`, `SIN_PESTANA`…), nunca el contenido. Con él la auditoría dice por qué un MCP no conectó.
- **La auditoría con el motor real** (`auditoria.py`, fuera del sandbox):
  `python3 -m arquitectura.auditoria --salida DIR` corre cada motor instalado por los dos caminos (la terminal con
  `sesion.para_lanzar` y la página con lo mismo que le pone la página: `pagina_v2.nucleo_para` y, en OpenCode, el
  servidor que ella prende) con una sola pregunta, y mira la evidencia: la marca de `tarea_actual` en el registro (MCP),
  los momentos del registro (hooks) y la palabra de una skill del cerebro (skills); de la misma corrida salen las demás
  piezas del plan. Lo guarda para Conexiones y el doctor (`--no-guardar` para no hacerlo). Red de seguridad: la huella
  de la config global de cada motor, antes y después.
- **Fusión en el proyecto** (`nucleo._fundir`, paso `fundir` de una ficha): el servidor `workspace` se SUMA al JSON
  de MCP del proyecto (Cursor `.cursor/mcp.json`, Antigravity `.agents/mcp_config.json`) sin tocar lo del socio ni
  `workspace-memoria`, apuntando al lanzador fijo; si ese JSON no se puede leer, no se toca. `nucleo.mcp.ajustes`: la
  aprobación va dentro del único `--settings` que ya trae la corrida (Antigravity).
- **Los permisos de un agente en sandbox** (`permisos.sin_auto`, `engines/claude_code.en_sandbox`): nunca el modo
  automático, venga del lanzador, del comando o de un `defaultMode` del cerebro. En Claude Code, `dontAsk` con su
  sandbox (sin preguntas dentro, nada fuera) y `permissions.disableAutoMode: "disable"` en los ajustes de la sesión.

## 11 · El modo chat: el agente en la página y el hub

- **La guía, siempre activa** (`modo_chat.guia`): reglas cortas de chat (corto y lo esencial primero; archivos con
  `mostrar_archivo`; elegir con `preguntar` y opciones; skills con `usar_skill`, `reportar_avance` y su `fin`; sin `---`,
  sin menús de terminal ni la sintaxis de las herramientas; el cierre 🧠 del cerebro en una línea). Llega a todo motor
  en la conversación de la página o del hub por la vía de su ficha, `nucleo.chat`: «argv» = con el tono en la pieza de
  sistema de la sesión, solo con `WORKSPACE_VIA=pagina` (`nucleo.guia_chat`; Claude Code); «mensaje» = la página la
  manda UNA vez por conexión antes de tu primer mensaje (`pagina_v2.guia_para`; los demás), y la conversación guarda solo
  lo tuyo. Sin núcleo, con el comando de respaldo de cada herramienta. Con el paquete apagado, la página como antes. La
  skill `workspace-pagina` queda para el detalle.
- **`mostrar_archivo`** (MCP núcleo; respaldo `workspace pasos archivo <ruta> [--titulo …]`): un archivo que existe
  DENTRO del cerebro (la ruta real, siguiendo enlaces) va al registro de la pestaña (`registro.ARCHIVO`, o al buzón del
  cerebro si el sandbox del motor no deja escribir el registro) y la página lo pinta como tarjeta con «Abrir» y
  «Mostrar en la carpeta» (`localhost_front.abrir`, que vuelve a comprobar que está dentro) en el turno donde se enseñó,
  después de su texto. Uno de fuera, nunca.
- **La limpieza del lado de la página** (`modo_chat.limpiar`, en `pagina_v2.conversacion` y en el texto en vivo): sale la
  sintaxis interna conocida de un motor (el `▤…▤` de Codex), un enlace a un archivo del cerebro pasa a ser su tarjeta
  (uno de fuera queda como texto, nunca tarjeta) y se van los `---` sueltos. Lo de dentro de un bloque de código no se
  toca, y el historial guarda lo que escribió tal cual.
- **«Terminó» al final** (B43, `50_chat.js · pintarHilo`): la tarjeta va después del mensaje final de su turno (antes de
  tu siguiente mensaje o de la marca de otra skill); con el turno en curso, abajo de lo que escribe en vivo.

## Lo que falta verificar (lo dice el probador)

- Las rutas y dialectos de hooks fuera de Claude Code: la carpeta de extensión de Agent
  Plugins (`codex/`, `cursor/`, `kiro/`, `hermes/`), el formato exacto del manifiesto de
  Codex, el YAML de hooks de Hermes y la API de plugins V2 de OpenCode.
- Las líneas `probador.corrida` y `probador.preparar` de las 9 fichas (`verificado: false`).
- Windows: los hooks llaman `python3`.
