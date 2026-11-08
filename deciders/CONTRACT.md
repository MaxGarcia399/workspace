# Decisores enchufables de Workspace — contrato

Un **decisor** elige entre opciones **fijas** y dice qué tan seguro está. No programa ni
conversa (eso es un motor, `engines/`). Calca el patrón de `engines/CONTRACT.md`: la lista
real es **`deciders/*.py` sin `_` inicial** (`decisions.deciders()`), y agregar uno no toca
nada más.

| Decisor | Archivo | Dónde corre | Para qué |
|---|---|---|---|
| `rules` | `rules.py` | esta computadora, sin IA | **interno** (`internal: True`): pruebas y `tools/decisores_live_check.py --dry`; ninguna pantalla lo muestra |
| `jev` | `jev.py` | nube (TypeSafe) | solo la llave (entorno `TYPESAFE_API_KEY` o bóveda de Workspace): habla con la API con la **stdlib**, sin SDK (el oficial pide Python 3.10+ y Workspace corre en 3.9+); sin llave → `ok: False, error: "no_key"` |
| `stub` | `stub.py` | esta computadora | eco para pruebas (`internal: True`, `offer: False`) |

`decisions.offered()` = los que ve el socio (sin `internal` ni `offer: False`). Los internos
**no se pueden elegir** como modelo (`decisions.selectable`): ni el general ni el de un uso, ni
por `workspace settings`; uno que quedó guardado no cuenta (modelo general → `off`, el de un uso
→ `general`). El stub respondería siempre la opción 0 al 100 %. Solo las pruebas los habilitan
(`WORKSPACE_DECIDERS_INTERNAL=1`, que pone `tests/_testutil.py`; un fixture de la QA en
`deciders/` lo necesita también). Un valor viejo `rules` se migra en silencio: modelo general →
`off` (y se guarda); el modelo de un uso → `general`.

## Interfaz (stdlib, falla-suave)

```python
META = {"id": "jev", "label": "Jev", "local": False, "kinds": ["choice", "score"], "offer": True,
        "key_env": "TYPESAFE_API_KEY",   # opcional: el decisor usa llave
        "provider": "TypeSafe", "site": "typesafe.ai",
        "context_tokens": 32768,         # límite de ENTRADA (medido con llamadas reales)
        "overhead_tokens": 300,          # tokens fijos por llamada (medido: 301 sin contexto)
        "token_factor": 1.0,             # opcional: corrección de fábrica (se calibra sola)
        "price_in_per_m": 0.042, "price_out_per_m": 0.0, "approx_price": True}

def decide(req: dict) -> dict:
    # req = {"kind": "choice"|"score", "question": str, "options": [str, ...],
    #        "criteria": {opción: descripción} (puede venir vacío),
    #        "context": str (YA sin secretos), "point": "<id del punto>", "timeout_ms": 1500}
    # → {"choice": str|None, "score": float|None, "probs": {opción: p}, "ms": int,
    #    "cost_usd": float|None (uso real × precio del META), "tokens": {"in", "out"}|None,
    #    "decider": "<id>", "ok": bool, "error": CÓDIGO|None, "error_detail": {…}|None}

def status() -> dict:          # opcional, barato y sin red
    # → {"ready": bool, "detail": str}   (jev: "no_key" | "cloud")
```

- `decide` **jamás levanta**: cualquier problema → `ok: False` + `error` = un **código**
  (`context_too_large` · `auth` · `payment` · `rate_limit` · `timeout` · `connection` ·
  `server` · `not_found` · `bad_request` · `bad_response` · `no_key` · `need_options` ·
  `error`; la fachada agrega `out_of_options`, `not_installed`, `off`, `use_off`) y
  `error_detail` = `{status, type, request_id}` de una respuesta HTTP o `{class, phase}` de un
  fallo de red (`connect` / `read`), sin la llave. Jev clasifica por el STATUS y el
  `detail.error_type` (400/413/422 con max_tokens → `context_too_large`, 402 o
  «insufficient_*» → `payment`…), no por el texto.
- **Mensajes para personas: `decision_errors.py`** — `human(código, decisor, …)` (Preguntar,
  Motores → Probar, la CLI y la herramienta MCP), `short(código)` (Historial) y
  `detail_lines(error_detail)` («d detalle» en la caja del resultado). El mensaje principal
  SIEMPRE trae el siguiente paso (402 → «recarga crédito en typesafe.ai»; timeout → «intenta de
  nuevo o usa menos contexto»; sin conexión → «revisa tu internet»; uso apagado → «actívalo en
  Decisores → Ajustes»…) y jamás lleva URL, request_id ni nombres de clase.

## Jev sin SDK (`deciders/jev.py`)

- `http.client` + `json` + `ssl` (Python 3.9+): `POST {TYPESAFE_BASE_URL o
  https://api.typesafe.ai}/v1/systemone` con `Authorization: Bearer <llave>`, `Accept` y
  `Content-Type: application/json`; cuerpo `{"state": {"context"}, "model": "jev-latest"
  (TYPESAFE_DEFAULT_MODEL), "questions": {"q": {"type": "choice", "instructions", "criteria"}}}`;
  respuesta `answers.q.{choice, confidence, probabilities}` + `usage`. Es **byte a byte** la
  petición del SDK oficial 0.7.5 (`tests/fixtures/decisores/typesafe_systemone_0.7.5.json`,
  grabada una vez; la prueba de paridad no importa el SDK). Comprime con zstd como el SDK solo si
  el Python lo trae (3.14+) y el cuerpo pasa de 1 KB. Se presenta como Workspace (`User-Agent`).
- La llave **solo viaja por https** (o por http a esta misma máquina: `localhost`,
  `127.0.0.1`, `::1`, para el simulador de la QA): un `TYPESAFE_BASE_URL` con `http://` a otro
  host falla con `insecure_url` sin conectar. La respuesta se lee hasta 4 MB y, descomprimida
  (gzip, deflate, zstd), hasta 8 MB: más es `bad_response`.
- Sin reintentos. Conexión con su propio tiempo (≤ 3 s; un host que no contesta es
  `connection`, no `timeout`); la lectura usa lo que quede. `HTTPS_PROXY`/`NO_PROXY` del
  ENTORNO (como el SDK; túnel CONNECT). Un proxy configurado pero mal escrito (`::bogus::`,
  `http://`, `http://[::1`, puerto que no es número, `socks5://`…) NO se ignora — eso mandaría
  directo, saltándose el proxy —: falla con el código `proxy` («El proxy configurado
  (HTTPS_PROXY) no es válido · corrígelo o quítalo»); el detalle nombra la variable, jamás su
  valor. TLS siempre verificado: las CAs del sistema y, si el Python no trae ninguna (el de
  python.org en Mac), certifi o `/etc/ssl/cert.pem`.
- `criteria`: una línea por opción (`decisions.SPECS[<uso>]["criteria"]`) que dice qué
  significa cada una; Jev la manda como la descripción de la etiqueta en `Choice`.
- `score`: sin opciones se usan `["yes", "no"]`; el score es la probabilidad de la primera.
- El tiempo límite lo impone la fachada (hilo + `join`); al vencer, `error: "timeout"`.
  Jev además pide sin reintentos y con ese mismo tiempo por petición.
- La fachada valida la respuesta: la elección debe ser una de las opciones y las
  probabilidades se recortan a las opciones; se normalizan SOLO si cubren todas. Si no, la `p`
  de la elegida es la cruda (0–1) y, si falta, `p_known: false`: con «decide» eso NO aplica
  (se porta como «sugiere»). Una probabilidad que no vino jamás vale «100 % seguro».
- **Pausa tras un fallo de red** (`decisions.BREAKER_S` = 60 s): tras `connection` o
  `timeout` de un decisor en la nube, los usos automáticos (hooks, agentes) no lo vuelven a
  llamar durante la pausa y responden ese mismo código al instante, con `error_detail:
  {breaker: true, retry_s}` (también en la CLI y la herramienta MCP) y el mensaje «<modelo> está en
  pausa ~Ns tras un fallo de red · reintenta en un momento» — nunca «sin conexión» ni «tardó».
  Un decisor que se rinde solo antes del tiempo límite de Workspace dice «no respondió a
  tiempo», sin un número de segundos que no se esperaron. La
  pausa vive en `<estado>/decisions-breaker.json` (la comparten hooks, CLI y MCP) y guarda
  CUÁNDO se abrió: una hora del futuro (un reloj adelantado) cuenta como vencida. Preguntar a
  mano sí llama, un acierto la cierra y el chequeo en vivo (`consult(..., breaker=False)`) ni la
  mira ni la abre.

## Fachada: `decisions.py`

- **`gate(point, context, …)` — la semántica de los niveles, en un solo lugar.** Devuelve
  `None` (apagado, falló o tardó: **el punto sigue exactamente como hoy**) o un veredicto
  `{mode, choice, p, decider, level, threshold, id, message}`:

  | nivel del uso | `mode` | qué hace el punto |
  |---|---|---|
  | `off` | — (`None`, ni se llama) | nada |
  | `observe` | `observe` | nada; solo queda en la bitácora |
  | `suggest` | `suggest` | muestra la respuesta (contexto del hook, mensaje al agente o al socio), no la aplica |
  | `decide`, p ≥ umbral | `apply` | la aplica |
  | `decide`, p < umbral | `suggest` | como suggest |

- `ask(...)` → el dict crudo o `None`; `consult(...)` → **siempre** un dict (la sección).
- Antes de salir, `redact()` quita secretos, en dos fuerzas:
  - **Fuerte** (la pregunta y el contexto): bloques PEM de llave privada **enteros** (BEGIN … END,
    cualquier tipo; uno cortado, hasta el final), los formatos inequívocos de proveedor de
    `secret_scan` (`sk-…`, `ghp_…`, `xox…`, `AKIA…`…) y los extra (webhooks de Slack, Discord,
    Teams y Zapier, el token de un bot de Telegram, `glpat-…`, `npm_…`, `GOCSPX-…`), la
    contraseña de una URL (`esquema://u:clave@host`), lo que va tras `Bearer` o en
    `Authorization:` y los valores literales de la llave del entorno y de la bóveda.
  - **Amplia** (solo el contexto): además los demás patrones de `secret_scan` y:
    - «nombre = / : valor» con una **palabra fuerte** (`password`, `passwd`, `pwd`,
      `contraseña`, `pass`, `secret`, `token`, `api_key`, `auth`, y `*_SECRET`, `*_TOKEN`,
      `*_PASS`, `*_KEY`): entre comillas, CUALQUIER valor de 4+ (también con espacios: una
      frase de paso); sin comillas, 4+ con forma de secreto (dígito o símbolo), o solo letras
      si es lo último del renglón — «Contraseña del wifi: casaazulgrande» sale, «Contraseña:
      pídesela a recepción» se queda. Nunca `true/false/null…`, referencias (`${VAR}`,
      `{{ secrets.X }}`, `<tu-llave>`) ni, sin comillas, expresiones de código;
    - **«clave»** a secas puede ser un código («Clave del producto: SKU-12345», «Clave de la
      tienda: 0042», «clave foránea: cliente_id»): solo cuenta con frase de contraseña («clave
      de acceso / del wifi / secreta / de la API / de la cuenta / privada») o con forma clara de
      secreto (un símbolo que no sea `- _ .`, o mayúsculas, minúsculas y dígitos con 8+), y nunca
      un identificador;
    - asignaciones de código con tipo (`password: str = "…"`), por índice
      (`config["password"] = "…"`, `os.environ["DB_PASSWORD"] = "…"`), f-strings y «la
      contraseña / clave del wifi es X»;
    - credenciales de línea de comandos sin palabra clave (`curl -u u:clave`, `mysql -p…`,
      `--password`, `PGPASSWORD=`, `sshpass -p`, `auth=(…)`);
    - hex/base64 largos **solo con contexto**: en asignación o encabezado (`nombre: valor`,
      `nombre=valor`, también en el query de una URL) salvo nombres que no son de secretos
      (`id`, `sha*`, `commit`, `version`, `path`, `url`…), en una bandera (`--nombre valor`) o con
      una palabra de secreto (o «valor») poco antes. Un SHA suelto, una ruta o el id de una URL
      se quedan; un valor encontrado se quita también donde se repita.

    Medido: las 40 formas realistas de la revisión, 40/40 (antes 25/40); en tres cerebros
    sintéticos realistas (con «Clave del producto: SKU-…», «Contraseña: pídesela…», SHAs, rutas y
    URLs), 0 archivos sin secretos cambiados y todos los que traen uno, redactados.
  - **Las opciones jamás se redactan**: son etiquetas del agente; la elección vuelve con SU texto,
    byte a byte, y su `index`. Pero una opción con forma INEQUÍVOCA de llave (`tiene_llave`:
    formatos de proveedor, webhooks, PEM, credenciales en URL, un JWT suelto, un valor de la
    bóveda) **no se manda**: `bad_input` «Una opción parece una llave · quítala» (la CLI sale con
    2), y en la bitácora las opciones van siempre con la redacción fuerte. Un JWT suelto
    (`eyJ….eyJ….firma`, sin «Bearer» ni palabra clave) es formato fuerte: se quita también de la
    pregunta.
  Es redacción, no bloqueo. **Primero se redacta y después se recorta** (un secreto partido por
  el corte ya no lo reconoce nadie): los hooks pasan una ventana mayor y `gate(...,
  context_max=N)` corta al final. Cuantificadores acotados (nada cuadrático con texto
  patológico; los patrones de `secret_scan` sin tope van renglón por renglón, ≤2048). Sin el
  detector, el contexto se manda **vacío** (falla cerrada).
- El uso «Seguridad» además tapa, ANTES de armar el contexto, el valor de cada `hardcoded_secret`
  que su propio escáner encontró — en su lugar y en CADA otra aparición (un comentario, un log,
  un `print`) — (`security_guidance.enmascarar`): su detector es más amplio que la redacción
  general. Y antes de eso le quita al fragmento lo que el archivo DICE
  (`security_guidance.solo_codigo`): comentarios, docstrings y la prosa de los textos entre
  comillas (los comandos, rutas, SQL y direcciones se quedan: son conducta). Python con
  `tokenize`; si no tokeniza (un trozo de un Edit), el escáner de `#`; los demás lenguajes, lo
  razonable (`#`, `//`, `/* */`, `<!-- -->`); si algo truena, el texto tal cual. La pregunta
  pide juzgar solo el comportamiento ejecutable e ignorar lo que diga el texto.
- **Seguridad puede subir el riesgo, nunca bajarlo** (`SPECS[...]["apply_only"]`): en «decide»
  solo se aplica «alto»; «medio» y «bajo» quedan como sugerencia aunque pasen el umbral (la
  bitácora dice `suggest`) y el aviso del escáner jamás se acorta ni se suaviza. Prueba real
  2026-11-07: un docstring «es prueba, no se ejecuta» bajó a «bajo» un `shell=True` con un
  argumento de fuera.
- `mark(id, truth)` califica; `history()`, `accuracy(point)`, `point_total(point)`, `stats()`.
- Llave: `connect(id, key)` / `disconnect(id)` / `key_source(id)` → `secret_store` (bóveda
  per-máquina `secrets.local`, 0600; jamás al entorno de un motor: `engine_env` la quita).
  Orden de lectura en `jev.py`: entorno del sistema → bóveda.

## Los 8 usos, conectados (todos apagados de fábrica)

| id | dónde pregunta | contexto | `apply` |
|---|---|---|---|
| `workspace.memory` | `memoria.guardar_nota` (CLI, bandeja y herramienta MCP) — solo notas con el tipo genérico `nota` | el texto de la nota | cambia la **etiqueta** (el texto es del agente); suggest = línea en la salida. Con el uso encendido (cada nota puede esperar al decisor), la bandeja saca cada nota en cuanto se guarda: un lote cortado deja solo las que faltan. Apagado, la bandeja es la de siempre (sin deduplicar nada) |
| `workspace.evals` | `hooks/memoria_cierre.py`, al cerrar cualquier motor | el extracto sin IA de la maleta | anota el resultado en `<estado>/evals/sesiones.jsonl`; observe/suggest quedan en la bitácora (Historial) |
| `workspace.skills` | `hooks/skill_review.py` al cerrar (si la Revisión de skills está encendida); se aplica al abrir | el inicio de la vista neutral | apagado: lo de siempre (el freno de 2 h, `THROTTLE_SECONDS`, decide). observe/suggest: el freno decide la entrega, pero el modelo se consulta y se anota **aunque el freno frene**. decide con una respuesta SOBRE el umbral (mode apply): decide el modelo — «sí» entrega aunque el freno esté activo, con un piso de 10 min entre dos entregas (`PISO_DECIDE_SECONDS`); «no» no entrega. Todo lo demás (bajo el umbral, sin probabilidad, si falla o en la pausa) es lo de siempre: el freno decide, y la línea de la última sesión dice lo que pasó («sin revisión: hubo otra hace poco», «solo una sugerencia: la revisión se entregó igual»). suggest = + la estimación en la tarea |
| `workspace.security` | `hooks/security_guidance.py`, **solo** si el escaneo N15 ya encontró algo | archivo, clases y **solo el código** del fragmento | solo «alto» → pide corregir antes de seguir; lo demás es sugerencia (puede subir el riesgo, nunca bajarlo); jamás se borra, acorta ni bloquea |
| `agents.choose` | el agente: `workspace decidir` / herramienta `decidir` | lo que el agente mande | el agente usa la opción |
| `agents.review` | ídem (opciones de fábrica: completo / falta algo) | `request` = lo que pidió el socio + `context` = el entregable, que viajan como «SE PIDIÓ: … / SE ENTREGÓ: …»: lo pendiente o fuera de alcance que el entregable declara no cuenta si no estaba en el pedido | ídem |
| `agents.prompt` | ídem (opciones = variantes; responde también `index`, como todos los usos de agentes) | ídem | ídem |
| `agents.route` | ídem (sin opciones = los agentes registrados) | ídem | ídem |

Correspondencia con los ids del borrador: `memoria.tipo` → `workspace.memory`,
`evals.resultado` → `workspace.evals`, `skills.amerita` → `workspace.skills`,
`seguridad.riesgo` → `workspace.security`, `hub.ruta` → `agents.route`. La pregunta y las
opciones fijas de cada uso viven en `decisions.SPECS` (las mismas en el hook, la CLI y el
chequeo en vivo). Las preguntas a mano de la sección usan el punto `manual`.

## Para los agentes

- **La forma segura: `workspace decidir --stdin`** con UN objeto JSON por la entrada estándar
  (`{"point", "question", "options": [...], "context", "request"}`, UTF-8, BOM tolerado; los argumentos
  quedan fijos). El texto que escribe el modelo **nunca** va en argv: en Windows el shim
  `workspace.cmd` deja que cmd.exe reinterprete `%VAR%`, comillas y `&` (la QA hizo correr un
  `echo` con una pregunta). Entrada que no sirve → JSON `{error_code: "bad_input"}`, rc 2; sin
  `|` (stdin = la terminal, o NUL en Windows) responde eso al instante en vez de esperar.
  `options` tiene que ser una LISTA de textos (como en la herramienta MCP): un texto «a,b» es
  `bad_input` (antes se partía por las comas). `workspace decidir --help` muestra `--stdin`
  primero, con un JSON de ejemplo, y marca el texto en los argumentos como desaconsejado.
  Verificado en Windows por Git Bash (pipe y heredoc), pwsh 7, cmd.exe (`type f |`, `< f`), el
  `.cmd` lanzado con lista de argumentos y `py front.py`. **Windows PowerShell 5.1** codifica lo
  que manda por `|` con `$OutputEncoding` (ASCII por omisión): `¿ ñ €` llegan como `?`. Ahí,
  antes del pipe, `$OutputEncoding = [Text.UTF8Encoding]::new($false)` (o la herramienta MCP).
- **CLI con argumentos** (compatibilidad; ya no se anuncia) `workspace decidir --point <id>
  --question "…" --options "a,b" [--option "…"]… [--context "…" | --context-file -]`
  (también `workspace decide`; `--context-file -` lee BYTES y decodifica UTF-8, sin el salto de
  línea del final que agregan `echo` y PowerShell) → JSON
  `{ok, point, mode, choice, p, probs, decider, id, ms, message, display}` (`ms` = lo que
  tardó el decisor, el mismo número que la bitácora; también en un fallo que sí llegó a
  intentarse). `request` (o
  `--request`) = el pedido: en `agents.review` lo que pidió el socio, con el entregable en
  `context` (sin el pedido el juez no sabe qué entraba en el alcance). `display` = una línea
  para el socio («◆ <modelo>: tabla · 87 % · sugerido» / «… · aplicado»; «◆ <modelo>: no respondió ·
  decide el agente» si el decisor falló): la instrucción le pide al agente mostrarla tal cual
  cada vez que consulta. Sin `display` en observe, con el uso apagado o con una entrada que no
  se mandó. En `observe` **no** se le da la
  elección al agente (decide él; lo del decisor se anota para medir). Sale 0 aunque el uso
  esté apagado (`mode: off`). Si falla: `{ok: false, mode: "error"|"off", error_code, error
  (en palabras, con qué hacer), message (qué hace el agente: decidir como siempre)}`; con el
  modelo activo y el uso apagado, `error_code: "use_off"` («Este uso está apagado en Decisores ·
  actívalo en Decisores → Ajustes»); con un modelo configurado cuyo archivo no está (o que no se
  puede elegir), `error_code: "model_missing"` («El modelo configurado (X) no está · elige otro
  en Motores → Modelos de decisión», también en Ajustes). Un argumento que no sirve (un
  `--point` que no existe, una bandera desconocida) también es JSON `bad_input`, rc 2, en el
  idioma del socio — no el error en inglés de argparse. Sin `decisions.py` (o con uno roto),
  `workspace decidir` responde `{ok: false, error_code: "unavailable"}`, rc 2, sin traceback.
  `--json` se acepta (la salida siempre es JSON). Todo el
  texto que lee el agente (CLI, MCP, la instrucción de arranque y las líneas de los hooks)
  sigue `ui.lang`. `timeout_ms` (argumento o JSON) se acota a 200–10 000 ms; uno que no es un
  número finito (`Infinity`, `1e999`, `NaN`) usa el de siempre.
- **MCP**: herramienta `decidir` (`point`, `question`, `options`, `context`, `request`) en el servidor
  `workspace-memoria`, aprobada por nombre como las de memoria (Copilot, Cursor, Kiro,
  Antigravity) — **solo si hay un uso de agentes encendido** (`decisions.agent_uses_on`): con
  todo apagado el motor ve lo mismo que antes (ni la herramienta en `tools/list`, ni su
  aprobación, ni la frase en las instrucciones del servidor). Se vuelve a mirar en cada
  `tools/call`: apagada a media sesión, responde «no está disponible» sin llamar a nadie. No
  pide la pestaña (no escribe en el cerebro). Su descripción, la de sus campos y su frase en
  las instrucciones del servidor siguen `ui.lang`.
  Quitar lo nuestro (desinstalar) también quita una aprobación de `decidir` que haya quedado.
  Prender o apagar un uso de agentes cambia los archivos de Workspace del cerebro sin respaldo
  ni aviso: el agente de Kiro (`.kiro/agents/workspace.json`) con y sin `decidir` es nuestro, y
  `.cursor/cli.json` saca NUESTRA regla `Mcp(workspace-memoria:decidir)` al apagarlos (las
  reglas del socio no se tocan): apagado, los dos quedan byte-idénticos a los de 0.7.0.
- **Claude Code: sin reglas pre-aprobadas para la CLI.** `workspace decidir` pide permiso como
  cualquier comando: una regla `Bash(workspace.cmd decidir:*)` sobre el shim `.cmd` de Windows
  dejaba que cmd.exe reinterpretara lo aprobado (comillas, `&`). La ruta pre-aprobada es la
  herramienta MCP. (Las reglas de memoria de main, `Bash(workspace[.cmd] memoria:*)`, tienen el
  mismo patrón: previo a Decisores, fuera de este cambio.)
- **Aviso**: `decisions.agent_instruction()` — unas líneas en el paquete de la pestaña SOLO si
  hay un uso de agentes encendido: primero la herramienta MCP; si el motor no la tiene,
  `workspace decidir --stdin`.

## Lo que se ve (`decision_visible.py`)

Todo solo con Decisores **encendido** (un modelo y algún uso prendido); apagado no hay ni una
línea, ni un contador, ni inyección, ni archivos: todo sale byte-idéntico a antes. Observe es
en silencio: solo suggest y decide se ven.

**UN formato** para toda intervención: `◆ <modelo>: <qué hizo> · <NN %> · <aplicado|sugerido>` — «<modelo>» es siempre el nombre (META `label`) del decisor que respondió, nunca uno fijo
(`decision_visible.formato`; el nombre sale del META del decisor; sin el % si no dio su
probabilidad). **La regla del bloque ◆** va en la instrucción del agente SOLO si algún uso se ve
(sugiere o decide, también los de Workspace): «cuando Decisores haya intervenido en este turno
(te llegó una línea ◆ …), cierra tu respuesta con un bloque ◆: una línea por intervención, tal
cual llegó; si no intervino, no pongas nada». Y como un motor envuelto puede perder esa regla al
compactar, **cada línea llega con su recordatorio** («Muéstrale esta línea al socio en tu bloque ◆
al final de tu respuesta.»: `para_el_socio` en la respuesta de decidir y en el `--json` de
memoria; una línea más en la salida de memoria y en el aviso de Seguridad) — nada en observe ni
apagado. Cada canal le hace llegar su línea:

- **Agentes**: el campo `display` (arriba): «◆ <modelo>: tabla · 87 % · sugerido».
- **Memoria**: en la salida de `workspace memoria nota` / `guardar_nota` (y en `--json`, el
  campo `decisor.display`): «◆ <modelo>: guardé la nota como hecho · 88 % · aplicado» o «◆ <modelo>: la
  nota parece hecho · 71 % · sugerido» + cómo guardarla la próxima — nada si eligió el mismo
  tipo genérico con que se guardó (`nota`).
- **Seguridad**: «◆ <modelo>: subió el aviso a riesgo alto · 92 % · aplicado» o «◆ <modelo>: ve riesgo
  bajo; el aviso no cambia · 97 % · sugerido», al final del aviso (lo lee el agente) y, en
  Claude Code, como `systemMessage` del hook (lo ve el socio). Los listeners pueden devolver
  `systemMessage`; `neutral_hooks` los junta en `visible` y `workspace_hook` lo emite.
- **Evals y Skills (al cerrar)**: el veredicto (suggest/decide) queda en
  `<estado>/decisores/ultima-sesion/<cerebro>.json` y se ve UNA vez al abrir la siguiente
  sesión de ese cerebro: en el contexto de arranque del agente («muéstraselo al socio en tu
  primera respuesta, en un bloque ◆») y en los avisos de la apertura del hub
  (`dispatch._decisores_al_abrir`, solo con terminal y sin `-p`), una línea por uso: «◆ <modelo>: tu
  última sesión quedó «resuelta» · 88 % · aplicado».
- **Lo que el agente no vio** (Claude Code, el único motor con inyección por mensaje): cada
  línea de la bitácora trae `t` (hora precisa), `tab`, `cerebro` (una huella, no la ruta) y
  `agente` (su línea ya le llegó por su canal: decidir, memoria, Seguridad). En el siguiente
  mensaje, UNA vez, las de esa pestaña desde el mensaje anterior que no le llegaron: «Desde tu
  último mensaje, Decisores hizo (ponlo en tu bloque ◆):» + hasta 3 líneas y «y N más».
- **Historial**: cada fila dice qué cambió («nota → hecho», «aviso → alto», «agente → opción
  B») y la elegida, el efecto entero («aplicó: nota → hecho», «sugirió «bajo»», «observó · no
  cambió nada»); arriba, «hoy: 7 consultas · 1 aplicada · 3 sugeridas».
- **Ajustes → un uso**: junto al umbral, sus últimas 5 confianzas («últimas: 87 · 44 · 33 · 67
  · 93»), de la más vieja a la más nueva. El umbral de fábrica sigue en 90.
- **Barra de estado** (la de Workspace en Claude Code, Copilot, Cursor y Antigravity): «◆ Decisores:
  hoy 7 · 1 aplicada» (la cuenta junta a todos los modelos: etiqueta neutra), de la cola de la bitácora (≤256 KB, sin caché).
- **A media sesión** (Claude Code): al abrir se guarda la huella de la instrucción que recibió
  el agente (`<estado>/decisores/sesiones/`); si el socio mueve Decisores, el siguiente
  mensaje lleva UNA vez la instrucción nueva (o «ya no le preguntes al decisor ni cierres con
  el bloque ◆» si lo apagó), por el mismo canal que el tono.

## Bitácora

`<estado>/decisions.jsonl` (`paths.state_dir()`), append-only, local a la máquina; cada línea se
escribe con `atomico.anexar` (entera y sin pisarse aunque escriban varios procesos a la vez,
también en Windows; fin de línea LF). Una línea
por decisión: `{type: "decision", id, ts, t, tab, cerebro, agente, point, decider, kind, level, mode, q (≤160, ya
redactada), q_hash, options, choice, p, score, ms, cost_usd, tokens, act, ok, error (código),
error_detail, attempts (si Preguntar reintentó)}` — **nunca el contexto**. Calificar agrega `{type: "mark", ref, truth, ts}`; gana la última. Los
fallos también se anotan (`ok: false`); el Historial los muestra pero no se califican. `p` es
`null` si el decisor no dio la probabilidad de la elegida. El archivo nace **0600** (como la
bóveda). En Windows `chmod` no toca la ACL: la bitácora, su copia vieja, la bóveda
(`secrets.local`) y los demás archivos de estado de Decisores reciben una DACL **protegida**
(sin heredar la de la carpeta) con solo tu usuario y SYSTEM, al crearse o reescribirse y, los
que ya estaban, la primera vez que se usan en el proceso (`acl_privada`; stdlib, ctypes →
advapi32; si no se puede, una línea en `<estado>/logs/acl.log` y se usa igual). QA en Windows
(2026-11-07): `C:\Users\<socio>\.claude` daba lectura a `CodexSandboxUsers`. La bitácora **rota** al pasar de ~5 MB
(`LEDGER_MAX_BYTES`): queda UNA copia vieja, `decisions.1.jsonl`. El Historial lee solo la cola
(≤4 MB) de la bitácora y, si no alcanza para las últimas 5000, la de la copia vieja; la
calificación más nueva gana también entre las dos.

## Ajustes (`settings.py`, grupo `decisions`)

| clave | valor | de fábrica |
|---|---|---|
| `decisions.model` | id de un decisor u `off` (interruptor maestro) | `off` (ninguno activo) |
| `decisions.points.<id>` | `{level: off\|observe\|suggest\|decide, model: general\|<decisor>, threshold: 50–99}` | `{off, general, 90}` |

## Contexto de Preguntar (`decision_context.py`)

Solo la pregunta a mano de la sección; los hooks siguen con su contexto mínimo.

| nivel | qué va |
|---|---|
| `nada` | solo la pregunta |
| `pestana` | el resumen guardado de la pestaña más reciente del agente (el de fábrica) |
| `sesiones` | los resúmenes de las pestañas que el socio marque |
| `memoria` | `STATE/MEMORY.md`, `STATE/INDEX.md` y su memoria de Claude Code (`motores/claude-code/memoria/<socio>/`) |
| `cerebro` | todo el cerebro si cabe («todo»); si no, **lo más relevante** para la pregunta y sus opciones y, en lo que sobre, lo representativo — memoria e índices, luego lo más nuevo — hasta llenar el presupuesto. Si casi nada coincide (o aún no hay pregunta), la selección es «lo más reciente» |

- **Presupuesto** (tokens de contexto) = límite − sobrecarga (META `overhead_tokens`) −
  pregunta y opciones − max(1000, 10 % del límite), y nunca más que
  `decisions.context_budget` si es > 0. Límite = META `context_tokens` (MEDIDO: Jev 32 768);
  `decisions.model_limits[<id>]` solo puede bajarlo. Un modelo que no declara su límite usa
  por dentro uno prudente (`LIMITE_PRUDENTE` = 8000), pero no se dice como suyo: Modelos
  muestra «sin límite declarado» y un «no cupo» dice «no declara su límite».
- **El medidor de cada nivel** (los cuadritos y la línea de abajo, también «Nada» y el costo de
  `v`) cuenta lo que de verdad se manda y se cobra: el contexto + lo fijo de CADA pregunta (la
  sobrecarga del decisor, META `overhead_tokens`, y la pregunta con sus opciones). Antes solo
  el contexto: Pestaña decía ≈88 tokens y costó 394.
- **Tokens POR CONTENIDO**, no un cociente global: un pre-tokenizador como el de Qwen2 /
  Llama 3 corta el texto en piezas — palabra (≤ 6 letras = 1 token; si no, 1 por cada 4.5),
  dígito (1), racha de puntuación (1 por cada 1.5 signos), salto de línea o espacio suelto (1),
  letras CJK/hangul (1 por carácter). Medido con Jev en textos sintéticos: prosa 4.16
  caracteres/token, tabla numérica 1.25, dígitos 1.00, markdown 2.62 (±1.5 %). Encima, un
  **factor** por decisor se calibra solo: tras cada llamada que sale con ≥ 1500 tokens, un
  promedio móvil (α 0.3, rango 0.5–2) lo acerca a lo que contó (`usage.input_tokens` −
  sobrecarga). Vive en `<estado>/decisions_calibration.json` (no en ajustes). Un «no cupo» NO
  lo toca (no ensucia la cuenta de los demás cerebros). El medidor, `v` y el envío usan la MISMA
  cuenta (`estimate()` arma el contexto con la pregunta de ahora). Costo = tokens × META
  `price_in_per_m` (aproximado); el de una respuesta es el uso REAL × precio.
- **Relevancia**: FTS5 en memoria (bm25, tokenizador de `memory_index`) sobre trozos de ~1600
  caracteres, con un empujón a lo que el índice de memoria del cerebro rankea alto; sin FTS5,
  palabras con idf.
- **Cerebro grande** (uno real pesa ~8 MB): `corpus(cerebro)` redacta, trocea y cuenta UNA vez
  por archivo (caché en memoria por ruta + tamaño + fecha + la llave del entorno y la bóveda) y
  arma el índice FTS5 una vez por escaneo. La caché es LRU: a lo más 2 cerebros y ~48 MB entre
  todos (el actual se queda aunque solo él pase; el peso se mide con `sys.getsizeof` y las
  páginas del FTS5, ×1.5 + 4 MB: en un cerebro de 8 MB, 59 MB estimados contra 58 medidos),
  nunca guarda texto sin redactar (`mtimes` es solo stat) y `free()` la suelta toda al salir de
  la sección SIN esperar: una construcción en curso ve la cancelación entre archivo y archivo y
  se suelta sola; una pregunta nueva solo vuelve a rankear (~50 ms en 3.9).
  El armado en frío (~2 s en 3.9 para 8 MB) cede el GIL entre archivos y espera mientras el
  socio teclea. En la sección, el medidor se recalcula 0.4 s después de la última tecla (nunca
  en cada tecla; mientras, el valor anterior con «calculando…»), `v` arma el contexto en un hilo
  y el lector de teclas (`section_box.KeyReader`, también en Modelos y Motores) separa un Esc
  suelto de la tecla que viene detrás y dibuja una sola vez por ráfaga (pegar).
- **Privacidad**: todo pasa por `redact()`; fuera binarios, carpetas de trabajo (`.git`,
  `.obsidian`, `.claude`, `tmp`, `scratch`, caché…), conversaciones crudas
  (`motores/*/conversaciones/`, la maleta), nombres de llaves (`.env`, `*.key`, `*.pem`,
  `secret`, `credencial`, y en español `clave(s)`, `llave(s)`, `contraseña(s)`,
  `credencial(es)`, `secreto(s)` con cualquier extensión), archivos de más de 256 KB y **lo
  privado**.
- **Lo de otras personas** (cerebro compartido): «Cerebro» y «Memoria» nunca mandan las sesiones
  de otros socios (`STATE/sessions/<otro>/`), los perfiles salvo el propio (`STATE/users/`), la
  bandeja de entrada (`STATE/inbox/`), la memoria de motor de otros (`motores/*/memoria/<otro>/`)
  ni los insumos del cliente (cualquier parte de la ruta que empiece con `_` dentro de
  `deliverables/`). Quién eres sale de `sessions_registry.socio` (identidad →
  `.claude/socio.local` → …); sin saberlo, nada personal de nadie. La vista `v` cuenta lo que
  quedó fuera: «excluidos: N (de otros socios, conversaciones o privados)». Tampoco salen las
  conversaciones ni los registros: `chats/` (mensajes directos y el canal del equipo), `msgs/`
  (el bus entre agentes), `STATE/log-archive/`, `motores/*/conversaciones/` y la maleta.
- **Convención de privado** (nueva; los cerebros no tenían una): un `.md` con `privado: true`
  (también `privada`, `private`, `confidencial`, `confidential`; con true/sí/yes/1/on, `"privado": true`,
  un comentario al final o renglones en blanco antes del frontmatter) o con la etiqueta
  `privado` en `tags` (en línea, entre corchetes o en lista), o cualquier archivo dentro de una
  carpeta `privado/` (o `private/`), **nunca** se manda a un decisor.
- La primera vez que `memoria` o `cerebro` MANDAN contenido a un decisor en la nube, la caja de
  la respuesta lo dice («Esto mandó contenido de tu cerebro a TypeSafe…»). Se decide al mandar
  (no al elegir el nivel: ahí puede que aún no hubiera modelo) y se marca visto
  (`decisions.notices`) solo después de dibujarse; si nada salió (sin llave, sin conexión al
  conectar, proxy mal escrito) no se avisa ni se marca. Al elegir el nivel, mientras no se haya
  visto, el mensaje adelanta lo mismo sin marcarlo. No hay compuerta en cada pregunta.
- La bitácora guarda solo `ctx = {level, mode, tokens, sources (nombres), n_sources}`.
- **Si aun así no cabe** (`context_too_large`): `decision_context.ask()` reintenta con a lo
  más 0.6×, 0.4× y 0.25× del primer intento (vuelve a rankear y a llenar; siempre más chico
  que el anterior) y con el factor que el «no cupo» demuestra (límite real ÷ lo que se mandó)
  — hasta 3 reintentos; si cupo, la respuesta dice «recorté el contexto a ≈X tokens para que
  cupiera»; si no, «Jev admite ≈32k tokens; esta pregunta llevaba ≈X · elige Memoria o
  Pestaña». La respuesta dice siempre qué contexto llevó («contexto: Cerebro · lo más
  reciente · ≈29k tokens»). Se anota una sola vez (con `attempts`). Los hooks no reintentan.

## Motores → Modelos de decisión (`modelos_tui.py`)

La puerta de Motores (`motores_tui`, dos cuadritos) se abre desde el hub con `front._abrir_motores`:
si algún módulo de Decisores no carga, abre la pantalla de motores de siempre (`engines_tui`) —
instalar y conectar un motor nunca depende de Decisores — y el estado de los decisores en la
puerta es falla-suave.

Dónde se **consiguen** los decisores, UNA vez (Decisores es dónde **actúan** y nunca pide llave). MISMO diseño y manejo que la pantalla de motores de agentes
(`engines_tui`: `SB.pick_list` │ opciones, `SB.split`, las mismas fichas): a la izquierda los
modelos de `deciders/` con su estado; a la derecha las
opciones del elegido, aplicadas ahí mismo — Jev: **Llave · Probar · Info** (no hay nada que
instalar): **conectar / desconectar llave** (`key_env`: campo enmascarado en la columna →
bóveda; desconectar con confirmación), **probar** (una llamada real chica, sin bitácora: latencia,
tokens y costo) y las líneas de **contexto** (`context_tokens`, medido; Enter elige un límite
MENOR → `decisions.model_limits`) y **precio** (`price_in_per_m`, `price_out_per_m`;
`approx_price` lo marca «aprox.»). Sin modelos en `deciders/`, la pantalla lo dice.

- El **primer** modelo que queda listo, si no hay uno activo, se activa solo como
  `decisions.model` (aviso de una línea); los usos siguen apagados.
- En Decisores → Ajustes, la tarjeta de un modelo que no está listo dice «configúralo en
  Motores» y Enter abre esta pantalla con ese modelo elegido (como Agentes abre «Agregar
  agente»); al volver, Decisores refleja el estado nuevo.

## Chequeo en vivo

`tools/decisores_live_check.py` (fuera de la suite): casos etiquetados por uso (datos
genéricos) en dos juegos — **afinados** (`CASOS`, 5–7 por uso: con ellos se ajustan las
preguntas y los `criteria`) y **apartados** (`CASOS_HO`, 3 por uso: no se tocan; miden si lo
afinado generaliza). Reporta acierto, latencia p50/p95, llamadas, fallos, tokens y costo
(`--set tuned|heldout|all`, `--verbose` = cada caso con esperado, respuesta y
probabilidades); tope duro de 150 llamadas, sin bitácora; `--dry` con Reglas. Sin llave no
llama a Jev.

## Reglas

- Nada corre solo: solo pregunta un hook de una sesión visible, el agente o la sección (sin
  nada nocturno ni sin ventana).
- Falla-suave en todos lados, con 1.5 s de tiempo límite en los hooks; borrar `decisions.py`
  o `deciders/` deja todo como estaba.
- Credenciales solo del entorno o de la bóveda; jamás en ajustes, bitácora ni errores.
