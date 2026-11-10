# Decisores enchufables de Workspace — contrato

Un **decisor** elige entre opciones **fijas** y dice qué tan seguro está. No programa ni
conversa (eso es un motor, `engines/`). Calca el patrón de `engines/CONTRACT.md`: la lista
real es **`deciders/*.py` sin `_` inicial** (`decisions.deciders()`), y agregar uno no toca
nada más.

| Decisor | Archivo | Dónde corre | Para qué |
|---|---|---|---|
| `rules` | `rules.py` | esta computadora, sin IA | **interno** (`internal: True`): pruebas y `tools/decisores_live_check.py --dry`; ninguna pantalla lo muestra |
| `jev` | `jev.py` | nube (TypeSafe) | solo la llave (entorno `TYPESAFE_API_KEY` o bóveda de Workspace): habla con la API con la **stdlib**, sin SDK (el oficial pide Python 3.10+ y Workspace corre en 3.9+); sin llave → `ok: False, error: "no_key"` |
| `openrouter` | `openrouter.py` | nube (OpenRouter) | una llave, 10 modelos de decisión de varias marcas (de fábrica `~typesafe/jev-latest`; medidos con llave real el 2026-11-08: fuera `inception/mercury-decide`, 404, y `upstage/solar-decide`, se agota el tiempo; `cloudflare/clef` con la pista «lento», p95 1.7 s); el costo real llega en `usage.cost` |
| `liquid` | `liquid.py` | nube (Liquid) | `d1.1` (de fábrica) y `d1-ultra`; **sin zstd**, cuerpo ≤ 4.5 MB |
| `ollama` | `ollama.py` | **esta computadora** (Ollama ≥ 0.35.0) | sin llave ni costo; el modelo, entre los descargados; `local: True` = sin aviso de nube |
| `stub` | `stub.py` | esta computadora | eco para pruebas (`internal: True`, `offer: False`) |

Los cuatro reales hablan **System One** (el protocolo de Jev, que OpenRouter, Liquid y Ollama
implementan tal cual): el cliente vive UNA vez en **`deciders/_systemone.py`** (el `_` = no es un
decisor) y cada decisor es una **ficha de proveedor** encima — ver «La base System One» abajo.

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
        "key_env": "TYPESAFE_API_KEY",   # opcional: el decisor usa llave (= su nombre en la bóveda)
        "key_env_std": "…",              # opcional: la variable estándar del proveedor (solo entorno)
        "provider": "TypeSafe", "site": "typesafe.ai",
        "context_tokens": 32768,         # límite de ENTRADA (medido con llamadas reales)
        "overhead_tokens": 300,          # tokens fijos por llamada (medido: 301 sin contexto)
        "token_factor": 1.0,             # opcional: corrección de fábrica (se calibra sola)
        "price_in_per_m": 0.042, "price_out_per_m": 0.0, "approx_price": True,
        "models": [...], "default_model": "…"}   # opcional: trae varios modelos para elegir

def decide(req: dict) -> dict:
    # req = {"kind": "choice"|"score", "question": str, "options": [str, ...],
    #        "criteria": {opción: descripción} (puede venir vacío),
    #        "context": str (YA sin secretos), "point": "<id del punto>", "timeout_ms": 1500}
    # → {"choice": str|None, "score": float|None, "probs": {opción: p}, "ms": int,
    #    "cost_usd": float|None (uso real × precio del META), "tokens": {"in", "out"}|None,
    #    "decider": "<id>", "ok": bool, "error": CÓDIGO|None, "error_detail": {…}|None}

def status() -> dict:          # opcional y BARATO: sin red, o (un local) acotado y en caché
    # → {"ready": bool, "detail": str}   (jev, openrouter, liquid: "no_key" | "cloud";
    #   ollama: "ollama_missing" | "ollama_off" | "ollama_old" | "no_model" | "local",
    #   más "version", "models" y "model")

# opcionales (los usa la fachada si están):
def live_meta() -> dict: ...   # lo del META que depende de esta máquina o del modelo elegido
                               # (el límite de un modelo local, el precio de d1-ultra); SIN red
def models() -> list: ...      # [{"id", "decision"}] (o textos): los modelos para elegir
def model() -> str: ...        # el que se usa: el guardado si está en la lista; si no, el de fábrica
def normalize_model(name): ... # el nombre canónico (Ollama: «nimble» → «nimble:latest»); sin ella, tal cual
def key_source() -> tuple: ... # ("env"|"store"|"", variable): de dónde sale la llave
def warm() -> bool: ...        # un local: precarga en segundo plano (regresa enseguida)
def timeout_code(req) -> str:  # un local: qué significa un tiempo agotado AHORA ("loading")
def invalidate(): ...          # un local: olvidar el estado en caché (el socio cambió algo)
```

- `decide` **jamás levanta**: cualquier problema → `ok: False` + `error` = un **código**
  (`context_too_large` · `auth` · `payment` · `rate_limit` · `timeout` · `loading` ·
  `connection` · `server` · `not_found` · `bad_request` · `bad_response` · `no_key` ·
  `no_model` · `not_decision` · `need_options` · `error`; la fachada agrega `out_of_options`,
  `not_installed`,
  `off`, `use_off`) y
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

## La base System One (`deciders/_systemone.py`)

El cliente del protocolo, común a Jev, OpenRouter, Liquid y Ollama — lo que antes vivía en
`jev.py`, sin cambiar su conducta (la paridad byte a byte de Jev contra el SDK 0.7.5 sigue
verde): `build_request`, `send` (http.client, TLS, proxy CONNECT, topes de 4/8 MB, sin
redirecciones, conexión ≤ 3 s aparte de la lectura), `parse`, `cost`, la clasificación de
errores y `decide` (valida, arma, manda, clasifica, lee). Cada decisor le pasa su **ficha**:

| campo | qué es | Jev · OpenRouter · Liquid · Ollama |
|---|---|---|
| `base_url` / `base_url_env` | la dirección y la variable que la cambia | `api.typesafe.ai` (`TYPESAFE_BASE_URL`) · `openrouter.ai/api` (`OPENROUTER_DECISIONS_BASE_URL`) · `api.liquid.ai/decisions` (`LIQUID_DECISIONS_BASE_URL`) · `127.0.0.1:11434` (`OLLAMA_HOST`, como lo lee Ollama) |
| `path` | la ruta | `/v1/systemone` en los cuatro |
| `auth` | `bearer` o `none` (JAMÁS se manda `Authorization`) | bearer · bearer · bearer · **none** |
| `zstd` | comprimir un cuerpo de 1 KB+ (Python 3.14+) | sí · sí · **no** · no |
| `root_fields` | los campos de la raíz (uno de más da 400) | `state, model, questions` (+ `keep_alive` en Ollama) |
| `errors` | el clasificador | `typesafe` (Jev: status + `detail.error_type`) · `models` (OpenRouter y Liquid: el de TypeSafe, y un 400/404 por el modelo → `not_decision` o `not_found` con el modelo) · `ollama` (`{"error": msg}`: 404 = no descargado; 400 con «context» o 413 = no cupo; 400 «… is not a … decision model» o «unsupported model» = `not_decision`) |
| `max_body` | lo más que acepta el proveedor | — · — · 4.5 MB (uno mayor ni se manda: `context_too_large`) · — |
| `usage_cost` | la respuesta trae `usage.cost` (el costo REAL gana sobre uso × precio) | — · sí · — · — |

**Solo modelos DE DECISIÓN — tres barreras.** Ollama y OpenRouter también sirven modelos de
chat; un decisor jamás usa uno:

1. **La lista solo ofrece modelos de decisión.** OpenRouter y Liquid: su lista curada de ids de
   decisión (cualquier otro, p. ej. `openai/gpt-4o` o `meta-llama/llama-3.1-8b-instruct`, ni
   aparece). Ollama: solo los descargados con `"capabilities": ["decision"]` en `/api/show` (las
   familias conocidas, de respaldo si `/api/show` no responde); los de chat no se ofrecen, se
   cuentan («1 modelo de chat descargado no sirve para decidir»).
2. **Guardar valida.** `decisions.check_model` — lo usan `set_decider_model`, el ajuste
   `decisions.decider_models` al guardarlo (también desde `workspace settings set`) y
   `tools/decisores_live_check.py --model` — rechaza con el porqué en palabras uno de chat
   («smollm2:135m no es un modelo de decisión · elige uno de decisión…»), uno que no está, uno no
   comercial o uno que no se puede comprobar (Ollama apagado). El modelo de un USO es un decisor
   (`decisions.points.<id>.model`), nunca un id de modelo: un id de chat ahí es `ValueError`. Al
   LEER no se valida contra la red: un guardado que ya no sirve (de chat, o borrado) cae solo al
   primero de decisión, sin esperar a nadie, y Modelos lo dice en una línea («Uso
   nimble:latest: smollm2:135m no es un modelo de decisión»).
3. **El endpoint rechaza los de chat.** Ollama 0.40.15 responde 400 «model "smollm2:135m" is
   not a llama.cpp decision model» → `not_decision` (fixture
   `tests/fixtures/decisores/ollama_0.40.15/systemone_400_no_decision.json`); si `/api/show` ya
   dijo que no es de decisión, ni se pregunta. OpenRouter/Liquid: un 400/404 por el modelo →
   `not_decision` o `not_found` con el modelo en el mensaje («OpenRouter no encuentra el modelo
   X · elige otro…»), no un «rechazó la pregunta» genérico. **Falla cerrado:** el punto sigue
   como si Decisores estuviera apagado (`gate` → `None`).

**El modelo de cada decisor** (los que traen varios): ajuste `decisions.decider_models`
(decisor → modelo), validado contra su lista al guardar (barrera 2: uno que no sirve →
`ValueError` sin escribir; uno guardado que ya no está → el primero de decisión). El nombre se
normaliza en UN lugar (`decisions.normalize_model` → el `normalize_model` del decisor): al
guardar, al validar el ajuste (también desde `workspace settings set decisions.decider_models
'{"ollama": "nimble"}'`, que acepta un JSON) y en el chequeo en vivo — «nimble» y
«nimble:latest» son el mismo. Se elige en
Motores → Modelos de decisión. El chequeo en vivo mide otro con `--model` sin tocar el guardado
(`_systemone.MODEL_OVERRIDE`, solo en ese proceso).

**Llaves con nombre propio.** La llave de un decisor nuevo va a la bóveda como
`WORKSPACE_DECIDER_<ID>_KEY` (META `key_env`) — JAMÁS con el nombre estándar del proveedor:
`secret_store._strip_for_engine` quita del entorno de un motor toda variable con el mismo nombre
y valor que la bóveda, así que guardar la de OpenRouter como `OPENROUTER_API_KEY` le quitaba a
Hermes, OpenClaw u opencode la que el socio exportó a mano con el mismo valor. Orden de lectura
(`_systemone.key_source`): el nombre propio del entorno → la variable estándar del entorno
(`OPENROUTER_API_KEY`, `LIQUID_API_KEY`; una que puso la bóveda como llave de proveedor de motores
no cuenta: un motor no la hereda, así que un hook tampoco la vería) → la bóveda. En
`secret_store`, los nombres `WORKSPACE_DECIDER_*_KEY` se portan como `ENV_OVERRIDES`: `scrub_env`
quita solo la COPIA de la bóveda y respeta la que el socio fijó en su sistema; no son
`PROVIDER_KEYS` (jamás se cargan al entorno del hub: el decisor las lee de disco). Jev sigue con
`TYPESAFE_API_KEY` igual que antes. **Al entorno de un motor, jamás** (`secret_store.SOLO_WORKSPACE` / `es_solo_workspace`): `TYPESAFE_API_KEY` y toda `WORKSPACE_DECIDER_*_KEY` salen SIEMPRE de `engine_env` / `strip_from_environ`, aunque el socio las exporte sin guardarlas (ningún motor envuelto las usa); por eso una exportada a mano decide en el hub pero no dentro de las sesiones de un agente (la pantalla de la llave lo dice). Las ESTÁNDAR de un proveedor que un motor sí lee (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `LIQUID_API_KEY` —opencode la toma del catálogo models.dev, proveedor `liquid`—) se respetan: si el socio las exporta, es para sus motores. La redacción quita del contexto los valores de TODAS esas
variables (`decisions.key_names()`), además de los de la bóveda.

**Local (Ollama).** `status()` barato: conexión ≤ 0.3 s, lectura corta y caché de 5 s (vencido,
se refresca en segundo plano y responde el anterior); distingue no instalado (ni el programa ni la
app) · apagado · versión < 0.35.0 (`GET /api/version`) · sin modelo de decisión (`GET /api/tags`) ·
listo. Qué modelo es de decisión lo dice el propio Ollama: `POST /api/show` trae
`"capabilities": ["decision"]` (medido con 0.40.15 y nimble; en caché, con poco tiempo al
preguntar). Solo si no responde o no trae `capabilities`, las familias conocidas (`nimble`,
`tev1`, `kev`, `d3`, `strands-decider`, `clef-flash`, `pplx-decider-flash`, `d1`, `laya`,
`autotrust-jev`) son el respaldo. Solo los de decisión se ofrecen (los de chat se cuentan); las
de licencia no comercial (`nimble-v3`, OpenJev) ni se listan. El
límite de contexto sale de `POST /api/show` del modelo (en caché): `num_ctx` (la ventana que
Ollama carga), nunca más que `<arch>.context_length`; sin dato, 4096 (medido: nimble trae
`num_ctx 8192` y `context_length 262144` → 8192). Respuestas reales grabadas en
`tests/fixtures/decisores/ollama_0.40.15/`. Siempre directo (sin
proxy) a esta máquina; un `OLLAMA_HOST` de otra máquina ya no es «en esta computadora»
(`live_meta` → `local: False`: hay aviso de que el contenido sale y vale la pausa de la nube).
Las pruebas apagan el sondeo con `WORKSPACE_NO_LOCAL_PROBE=1` (`tests/_testutil.py`).

**Local frío.** Cargar un modelo no cabe en 1.5 s. Cada petición lleva `keep_alive: "30m"`, y
`warm()` (una petición mínima en segundo plano) precarga al **Probar** y al **encender un uso**
(`decisions.set_point` / `set_global_model` con un uso encendido → `decisions.warm`). Antes de
preguntar, `GET /api/ps` dice si el modelo está cargado: un tiempo agotado con el modelo en frío
es `loading` («<modelo> está cargando el modelo · intenta de nuevo en unos segundos»), no
«tardó» ni «sin conexión»; si vence primero el tiempo de la fachada, ésta le pregunta al
decisor (`timeout_code`, sin red). Ni `loading` ni un tiempo agotado local abren la pausa de 60 s
(`BREAKER_S` es solo para la nube).

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
  host falla con `insecure_url` sin conectar. Y para un decisor CON llave, la variable de la
  URL base solo vale si apunta a ESTA máquina o al mismo host de fábrica: cualquier otro destino
  (`OPENROUTER_DECISIONS_BASE_URL=https://otro`, puesto por un agente dentro de un motor) es
  `insecure_url` sin conectar (`_systemone.base_url`, revisión 2026-11-08). `OLLAMA_HOST` (sin
  llave) sí puede apuntar a otra máquina. La respuesta se lee hasta 4 MB y, descomprimida
  (gzip, deflate, zstd), hasta 8 MB: más es `bad_response`.
- Sin reintentos. Conexión con su propio tiempo (≤ 3 s; un host que no contesta es
  `connection`, no `timeout`); la lectura usa lo que quede. `HTTPS_PROXY`/`NO_PROXY` del
  ENTORNO (como el SDK; túnel CONNECT), salvo a esta misma máquina: a loopback JAMÁS por un
  proxy (por http la llave y el contexto le llegarían en claro). Un proxy configurado pero mal escrito (`::bogus::`,
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
- Llave: `connect(id, key)` / `disconnect(id)` / `key_source(id)` / `key_var(id)` →
  `secret_store` (bóveda per-máquina, fuera del cerebro; jamás al entorno de un motor:
  `engine_env` la quita). Orden de lectura en `jev.py`: entorno del sistema → bóveda; en los
  nuevos, nombre propio → variable estándar → bóveda (ver «Llaves con nombre propio» y «Dónde
  vive la llave»).

### Dónde vive la llave (bóveda v2, 2026-11-08)

`secret_store` guarda cada llave en el **llavero del sistema** detrás de la misma API
(`get`/`set_secret`/`remove`/`names`/`has`: los decisores no cambian):

- **macOS:** el llavero de inicio de sesión con `/usr/bin/security`; el valor va por la entrada
  estándar de `security -i` (en `ps` solo se ve `security -i`), en base64 y en trozos de 2000
  caracteres (la línea de `security -i` corta en 4096 bytes), y se lee con
  `find-generic-password -w`. Nunca `-U` sobre un elemento existente (con el llavero temporal de
  prueba, `security` se quedó esperando un diálogo): cada escritura crea elementos nuevos, los
  verifica, cambia el índice y borra los viejos. Antes de llamar mira, sin diálogo
  (`SecKeychainGetStatus`), que el llavero esté abierto; cerrado = sin llavero. VERIFICADO con un
  llavero temporal (`tests/test_secret_store_llavero.py`), sin diálogos.
- **Windows:** DPAPI de usuario (`CryptProtectData` con `CRYPTPROTECT_UI_FORBIDDEN`, por
  ctypes); el cifrado vive en `boveda/indice.local`, con DACL solo-dueño. Probado con un doble de
  ctypes; falta probarlo en la PC.
- **Linux:** `secret-tool` por la entrada estándar si existe y hay sesión de D-Bus; si no, el
  archivo 0600 de siempre con aviso. Probado con un doble del programa; falta en un Linux real.

`secrets.local` queda como el archivo v1 (texto plano 0600) y el respaldo de siempre: sin llavero
(o con el ajuste `otros.boveda` = `file`) todo se guarda ahí, y lo que tenga gana al índice. La
migración (`secret_store.migrar`, al arrancar, en la migración `202611081500_boveda_al_llavero` y
en cada escritura) respalda, mueve, verifica leyendo de vuelta y solo entonces vacía el archivo;
falla-suave y con deshacer (`workspace migrate --undo 202611081500_boveda_al_llavero`).
`workspace llaves` dice de dónde sale cada llave (entorno · llavero · archivo, y si ahora está
ilegible) y `workspace llaves auditar` busca restos en texto plano, sin imprimir valores. Tras
la revisión independiente (2026-11-08): solo la instalación activa migra; `update --rollback`
deshace antes de volver; `secrets.local` queda sellado (un hub viejo no escribe a medias); una
lectura fallida nunca termina en escritura; un tiempo agotado espera 1–15 min, no un día; en
Linux, colección bloqueada = sin llavero (sin diálogo); respaldos y archivadas caducan y quitar
una llave borra sus copias; leer toda la bóveda es un solo `security -i`. La bitácora, «d detalle» y la
salida de `workspace decidir` pasan por `secret_store.sin_valores` (tacha cada valor de la
bóveda, también los que viven en el llavero). Límite honesto: el llavero protege el disco, los
respaldos y la sincronización, no frente a un programa del mismo usuario: por eso los motores con
reglas niegan leer la bóveda y los comandos que piden una llave al llavero
(`rutas_protegidas.lectura_negada` y `COMANDOS_LLAVERO`).
- Modelo: `decider_models(id)` · `decider_model(id)` · `set_decider_model(id, m)`; `warm(id)`
  precarga uno local en segundo plano.

## Los 9 usos, conectados (todos apagados de fábrica)

| id | dónde pregunta | contexto | `apply` |
|---|---|---|---|
| `workspace.memory` | `memoria.guardar_nota` (CLI, bandeja y herramienta MCP) — solo notas con el tipo genérico `nota` | el texto de la nota | cambia la **etiqueta** (el texto es del agente); suggest = línea en la salida. Con el uso encendido (cada nota puede esperar al decisor), la bandeja saca cada nota en cuanto se guarda: un lote cortado deja solo las que faltan. Apagado, la bandeja es la de siempre (sin deduplicar nada) |
| `workspace.evals` | `hooks/memoria_cierre.py`, al cerrar cualquier motor | el extracto sin IA de la maleta | anota el resultado en `<estado>/evals/sesiones.jsonl`; observe/suggest quedan en la bitácora (Historial) |
| `workspace.skills` | `hooks/skill_review.py` al cerrar (si la Revisión de skills está encendida); se aplica al abrir | el inicio de la vista neutral | apagado: lo de siempre (el freno de 2 h, `THROTTLE_SECONDS`, decide). observe/suggest: el freno decide la entrega, pero el modelo se consulta y se anota **aunque el freno frene**. decide con una respuesta SOBRE el umbral (mode apply): decide el modelo — «sí» entrega aunque el freno esté activo, con un piso de 10 min entre dos entregas (`PISO_DECIDE_SECONDS`); «no» no entrega. Todo lo demás (bajo el umbral, sin probabilidad, si falla o en la pausa) es lo de siempre: el freno decide, y la línea de la última sesión dice lo que pasó («sin revisión: hubo otra hace poco», «solo una sugerencia: la revisión se entregó igual»). suggest = + la estimación en la tarea |
| `workspace.security` | `hooks/security_guidance.py`, **solo** si el escaneo N15 ya encontró algo | archivo, clases y **solo el código** del fragmento | solo «alto» → pide corregir antes de seguir; lo demás es sugerencia (puede subir el riesgo, nunca bajarlo); jamás se borra, acorta ni bloquea |
| `workspace.conversations` | `salas.esperar` (Conversaciones), con **tres preguntas** por `gate(question=, options=)` (`SPECS[…]["questions"]`, un solo `criteria` con las 7 opciones, sin repetir etiquetas): **C1** en el `esperar` del mencionado al llegarle un `pide` de otro agente (nunca lo del socio, lo que va a quien abrió, lo delicado ni lo urgente: espera ≤15 min) · **C2** en el `esperar` de quien abrió, cada 6 mensajes nuevos · **C3** en el `esperar` de quien abrió, al llegarle un `responde`. Seguridad de cada mensaje: el uso `workspace.security` con su pregunta (`SEGURIDAD_SALAS`) | título, objetivo, «hecho cuando» y los **resúmenes** (no los cuerpos); Seguridad, el cuerpo recortado con `solo_codigo` + `enmascarar` | C1 «solo informa» → no despierta y suelta la deuda («◆ solo informa»); C2 «en bucle»/«se desvió» → evento `pausa` «◆ …» (el socio reanuda); C3 «sí» → solo sugiere cerrar, en los dos niveles; Seguridad «alto» → «⚠ delicado» (solo sube). Al cerrar, `workspace.memory` sugiere el tipo del resumen y el comando `workspace memoria nota`. suggest = la línea ◆ sin cambiar nada. Apagado: todo igual, byte a byte |
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
(`secrets.local` y `boveda/`) y los demás archivos de estado de Decisores reciben una DACL **protegida**
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
| `decisions.decider_models` | decisor → modelo (los que traen varios; validado contra su lista) | `{}` (el de fábrica de cada uno) |
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
opciones del elegido, aplicadas ahí mismo — en la nube: **Llave · Probar · Info** (no hay nada
que instalar): **conectar / desconectar llave** (`key_env`: campo enmascarado en la columna →
bóveda; desconectar con confirmación), **probar** (una llamada real chica, sin bitácora: latencia,
tokens y costo) y las líneas de **contexto** (`context_tokens`, medido; Enter elige un límite
MENOR → `decisions.model_limits`) y **precio** (`price_in_per_m`, `price_out_per_m`;
`approx_price` lo marca «aprox.»; OpenRouter: «lo dice cada respuesta»). El estado de la lista es
el REAL (`status()`): listo · sin llave · no instalado · apagado · versión vieja · sin modelo.
Si el decisor trae varios modelos, la fila **modelo**: Enter (o un clic) **abre la lista**
(`section_box.pick_list`, la misma de todo el hub) con los modelos de decisión de ese decisor —
nunca uno de chat —, el actual marcado (●) y una pista por fila (la marca, el precio por M de
entrada o «en esta computadora»; si no cabe, gana el nombre entero); ↑↓ mueve, Enter elige y
guarda (`set_decider_model`, el aviso de una línea y de vuelta a las opciones con el nuevo a la
vista), Esc o ← cierran sin cambiar. Abierta, la lista usa la caja entera (el nombre largo y lo
medido caben juntos). **Lo medido manda:** si `<estado>/decisiones-medidas.json` (lo escribe el
chequeo en vivo completo) trae ese modelo, su pista es «95/97 · 0.3 s» (+ «· lento» si su p95 pasa
de 1.5 s, el tiempo límite de los usos) y los medidos van primero, por acierto y luego p95; sin
medición, la fila no inventa nada (marca, precio o «en esta computadora»). Con 10 o más
(OpenRouter), escribir filtra, con la línea de
búsqueda de la portada. En Ollama, los de chat descargados van en una línea al pie, no como
filas. Con un solo modelo, Enter no abre nada (lo dice). **Clics** (Mac/Linux; SGR-1006, como la
portada, solo mientras esta pantalla está abierta): cada fila de la lista, cada opción (como
Enter) y cada decisor de la izquierda; `section_box.KeyReader(mouse=True)` los entrega como
«mouse:x:y» y `frame.last_body_row/col` + `pick_list.last_rows` dicen qué fila fue. En Windows,
por ahora, teclado completo. Uno **local** (Ollama) no tiene llave: su fila de estado («en esta
computadora · 0.35.2»; Enter vuelve a mirar), el **siguiente paso** en una línea cuando no está
listo («Descarga un modelo de decisión: ollama pull nimble», «Abre Ollama…», «Actualiza Ollama a
0.35.0…»), precio «sin costo» y ningún aviso de nube; **probar** lo precarga antes. Sin modelos en
`deciders/`, la pantalla lo dice.

- **Tu llave, explicada** (fase A de llaves; spec `Llaves_Seguridad_v1`). La ayuda (`i`) tiene dos
  páginas, «qué es» y «tu llave» (Tab), para que ninguna pierda el wordmark grande; abre en «tu
  llave» si estás sobre una opción de la llave. «Tu llave, en simple · <proveedor>»: dónde vive
  (la bóveda de Workspace, fuera del cerebro), a dónde viaja (solo a su sitio, https, a esa
  dirección), quién la ve (puntos al pegarla; ni agentes, ni Historial; se borra de lo que se
  manda) y un consejo. Cada frase tiene su prueba en `tests/test_modelos_llave.py`
  (`CadaAfirmacionEsCierta`): si el código cambia, se pone rojo antes de que el texto mienta. Un
  decisor local solo dice «<modelo> no usa llave: todo pasa en esta computadora». Conectar
  recomienda «una llave solo para Workspace» y, SOLO si el META lo declara verificado
  (`key_spend_limit`: OpenRouter), «con tope de gasto»; `keys_url` (OpenRouter:
  `https://openrouter.ai/keys`) se muestra como texto, sin abrir nada. Desconectar dice cómo
  dejarla muerta: «revócala también en <proveedor> (<keys_url> o su sitio)». No dice «llavero del
  sistema» hasta la fase B.
- El **primer** modelo que queda listo (al conectar la llave, al probarlo con éxito o, uno
  local, al volver a mirar su estado), si no hay uno activo, se activa solo como
  `decisions.model` (aviso de una línea); los usos siguen apagados.
- En Decisores → Ajustes, con más de 4 tarjetas de modelo van en filas de 3 (↑↓ entre filas);
  debajo, dónde decide el enfocado: «en la nube · <proveedor>» o «en esta computadora».
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
llama a nadie. `--decider <id>` (de fábrica `jev`) y `--model <m>` miden cualquier decisor con
los MISMOS casos (el modelo, solo en esa corrida: el guardado no cambia); la última línea
(«resumen · <decisor>:<modelo> · acierto · p95 · costo») y `--json` (`acierto`, `p95_ms`,
`costo_usd`) sirven para compararlos. Un modelo nuevo no pasa de «sugiere» sin medirse así. Una
corrida COMPLETA (`--set all`, todos los usos, sin que el tope la corte) guarda su resultado en
`<estado>/decisiones-medidas.json` (`decisions.record_measure`: decisor, modelo canónico, acierto,
total, p95_ms, costo_usd, fecha, timeout_ms; jamás llaves ni casos; escritura atómica) y la lista
de modelos lo muestra; una parcial (`--points`, `--set tuned`, cortada por el tope, `--dry`) no.

## Reglas

- Nada corre solo: solo pregunta un hook de una sesión visible, el agente o la sección (sin
  nada nocturno ni sin ventana).
- Falla-suave en todos lados, con 1.5 s de tiempo límite en los hooks; borrar `decisions.py`
  o `deciders/` deja todo como estaba.
- Credenciales solo del entorno o de la bóveda; jamás en ajustes, bitácora ni errores.
