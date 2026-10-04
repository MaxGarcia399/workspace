# workflows/AUTHORING.md — cómo autorar un workflow (harness) en WORKSPACE

> **Qué es este documento.** El protocolo que un AUTOR (agente o socio) lee antes de crear o
> modificar un workflow. Es al `crear-harness`/`modificar-harness` lo que `skill-creator/SKILL.md`
> es a crear una skill: la guía leíble que convierte "quiero un pipeline para esta tarea" en un
> spec válido, seguro y descubrible. **Progressive disclosure:** lo HOT arriba (§1–§4, lo que
> necesitas siempre); el drill-down abajo (§5–§8, la gramática completa y el catálogo).
>
> **El meta-harness es dogfooding.** `crear-harness` y `modificar-harness` son ellos mismos
> workflows WORKSPACE que corren en el runner y se verifican con la misma maquinaria. Este doc es lo
> que sus pasos `agent` reciben como instrucción.

---

## 1. Cuándo algo ES un workflow (el disparo)

Un workflow es la respuesta correcta cuando la tarea es:

- **Repetible** — se va a hacer más de una vez (o para más de un cliente).
- **Con pasos verificables** — cada paso deja evidencia que una máquina puede leer (un exit code,
  el estado de git, un archivo con forma declarada), no solo "el agente dijo que lo hizo".
- **Con gates** — hay decisiones de riesgo o aprobación donde un humano debe entrar.

**NO es un workflow** (no lo fuerces a serlo):
- One-shot que no se repite → tarea directa.
- Pura prosa sin oráculo de máquina (redactar un texto, conversar) → es una **skill** o trabajo
  directo, no un pipeline. Un workflow todo-`agent` sin un solo `det` que verifique es humo.

El disparo tiene forma determinista: `workspace wf match "<texto de la tarea>"` empata los `triggers:`
de los specs contra el texto y devuelve candidatos. Si ya hay un workflow para esto, úsalo; no
dupliques (la fuga #1 de skills aplica igual: catálogo que miente).

---

## 2. La regla de oro de seguridad: COMPOSICIÓN, no PRIMITIVA

> **Un autor compone pasos que YA EXISTEN. Jamás inventa primitivas nuevas.**

- **Composición** = un spec JSON que ordena pasos del **registry cerrado** (`steps.known()`), con
  `when`/`output_schema`/`contract`/gates. Es **datos, no código**. Seguro para que lo autore un
  agente: no puede ejecutar nada que el registry no ofrezca ya, y todo se valida al cargar.
  → Esto es lo que hacen `crear-harness`/`modificar-harness`.
- **Primitiva** = un paso `det` nuevo (una función Python en `workflows/steps/`). Es **código
  arbitrario**. Un agente escribiéndolo sin revisión = ejecución no auditada = inaceptable para un
  cliente. → **Fuera del meta-harness.** Va por el pipeline de código (Turing + `/code-review` +
  tests). Si tu tarea NECESITA un paso det que no existe, el workflow lo **detecta y escala** (paso
  `clasificar-frontera` → gate `escalar-primitiva`): no lo improvises.

Por qué importa (client-safe): WORKSPACE se vende. Un harness que compone pasos allowlisted es
replicable y auditable; uno que deja a un agente escribir código nuevo es una superficie de ataque
(OWASP LLM01 inyección, LLM06 exceso de agencia). La frontera es la línea que no se cruza.

**Dónde vive la garantía (importante):** el **borde DURO** es `validate_spec` — rechaza AL CARGAR
cualquier `run:`/`verify:` fuera de `steps.known()`, así que una primitiva alucinada **nunca corre**
(muere en `validar-carga`/`smoke-dry`). El paso `clasificar-frontera` es un **asesor** de UX: adelanta
la detección para escalar temprano y con un mensaje claro, pero un agente que mal-etiquete una
primitiva como `agent` podría saltar ese aviso — y aun así el borde duro (`validate_spec`) lo atrapa.
No confundir: la seguridad es el validador, no el asesor.

**Invariante de despliegue (para venta):** el aislamiento de los pasos `agent` depende de que el
driver corra con `tools` DESACTIVADAS (postura de la casa: `TOOLS_NONE` siempre). Un despliegue de
cliente que inyecte un driver con manos (shell/fs) reintroduce agencia arbitraria — los `contract`
autorados pasarían a ser instrucciones ejecutables. **Cualquier deployment cliente debe fijar la
postura tools-off del driver.**

---

## 3. La decisión central: clasificar cada paso (det / agent / human)

Para CADA paso del workflow, decide su `kind`:

```
¿El paso se puede hacer con CÓDIGO que YA existe en steps.known()?
├── SÍ → det      (correr la suite, abrir un worktree, integrar, triage, evidencia…)  ← PREFIERE ESTO
└── NO → ¿Requiere JUICIO o GENERACIÓN (escribir, decidir, revisar prosa)?
         ├── SÍ → agent   (con contract de 4 partes + output_schema + verify de forma)
         └── ¿Es una DECISIÓN de riesgo / aprobación / algo SIN oráculo de máquina?
                  └── SÍ → human   (un gate; N2 = dueño del scope · N3 = identidad/estructura)
```

**Regla honesta (el límite del verify):** el verify determinista es tan fuerte como su **oráculo de
máquina**. Donde hay oráculo (suite → exit code, git → estado del repo, rutas/formas → existencia y
`output_schema`) la garantía es fuerte. Donde NO lo hay — pasos de **prosa/juicio** (`plan`,
`review`, `find`): ¿el plan es bueno?, ¿el review encontró lo importante? — el verify solo comprueba
**forma y existencia**, no calidad. Ahí el único gate honesto es el **humano**. **Nunca finjas un
verify determinista sobre prosa.** La madurez de un pipeline se mide en cuántos pasos migran de
agent/ad-hoc a **det**.

**Segunda dimensión — grados de libertad (calibra según la fragilidad):**
- Paso **frágil o irreversible** (integrar, promover, tocar main, borrar) → **baja libertad**:
  contract exacto, límites duros, y su gate es `human`. "Puente angosto con precipicios."
- Paso **abierto** (redactar un plan, explorar) → **alta libertad**: contract con objetivo y
  formato, sin sobre-restringir. "Campo abierto."
- El error de autor es uniformar: guardrails rígidos en un campo abierto (inútil) o sueltos en un
  precipicio (peligroso). Calibra por paso, explícitamente.

---

## 4. Cómo se autora, en 6 movimientos

1. **Arranca de un esqueleto válido, nunca de una página en blanco.** `workspace wf new <nombre>` crea
   `specs/<nombre>.json` que **ya pasa `validate_spec`** — un paso de cada kind, con `note:`
   explicando cada campo. Edita desde algo que funciona.
2. **Descompón la tarea** en pasos atómicos; clasifica cada uno (§3). Nombra el `run:` del registry
   para cada paso det (del catálogo, §7).
3. **Compón el spec**: mapea cada paso a `run`/`verify`/`contract`/`produces`/`reads`/`when`/
   `output_schema`; declara `triggers:` (para que sea descubrible) y `inputs:` (lo que varía por
   `--param`, para que sea replicable sin editar el spec).
4. **Valida al cargar**: `workspace wf run <nombre> --dry`. `--dry` es un ensayo: valida el spec
   (registry, integridad referencial de `reads`/`when`, `output_schema`) y muestra el plan sin
   ejecutar nada. Si algo falta, el error te dice **qué** (y sugiere el nombre correcto si fue un
   typo). Itera hasta que el dry salga verde.
5. **Pasa el checklist de calidad** (§6) antes de pedir aprobación.
6. **Gate de scope + promoción + registro**: un humano aprueba el scope (N2/N3); recién entonces
   el spec se **promueve** a `specs/`, aparece en `workspace wf list`, y `wf match` con sus
   `triggers` empata la tarea que lo motivó. *(En `crear-harness` el spec se autora en CUARENTENA —
   `specs/_pending/` — donde `wf run`/`list`/`match` NO lo ven: un spec sin aprobar jamás es
   corrible; `spec.promote` lo mueve tras el gate. Autorando a mano con `workspace wf new` el humano
   ya está en el loop y escribe directo a `specs/`.)*
   **Un workflow que no es descubrible es como si no existiera** (la fuga #1).

---

## 5. Anatomía del spec (drill-down)

Un spec es un JSON: `{workflow, version, steps:[...], triggers?, inputs?, note?}`.

**Top-level:**
| campo | obligatorio | qué es |
|---|---|---|
| `workflow` | sí | nombre (string) |
| `version` | sí | entero ≥1; un run empezado en vN termina en vN (spec congelado por-run) |
| `steps` | sí | lista no vacía de pasos |
| `triggers` | no | palabras clave que `wf match` empata contra el texto de la tarea (descubrible) |
| `inputs` | no | claves que llegan de FUERA por `--param`; habilitan `reads`/`when` sin productor upstream (replicable) |
| `note`/`map`/`guia` | no | comentarios; el runner los ignora |

**Por paso** (según `kind`):
| campo | kind | qué hace |
|---|---|---|
| `id` | todos | único, `[A-Za-z0-9._-]` |
| `kind` | todos | `det` · `agent` · `human` |
| `run` | det (req) | nombre en `steps.known()` — la acción; typo = error al cargar con sugerencia |
| `verify` | det/agent | función del registry que lee la evidencia real tras el paso |
| `on_fail` | todos | `stop` (def) · `retry` |
| `max_iter` | retry (req) | entero 1..20 |
| `idempotent` | todos | bool (def true); un paso efectivo NO idempotente declara `false` (no combinable con retry) |
| `timeout` | todos | segundos (0<t≤86400); lo honran suite/worktree/driver real |
| `produces` | det/agent | claves de artefacto que el paso deja (el contrato aguas abajo) |
| `reads` | agent | claves que el driver recibe en su brief cerrado; deben tener productor upstream o venir de `inputs:` |
| `when` | todos | predicado declarativo (§8); falso ⇒ el paso queda `skipped` y el run sigue |
| `output_schema` | det/agent con `artifact` | contrato de FORMA del artefacto, validado ANTES del verify |
| `artifact` | agent | clave/archivo que el paso commitea |
| `contract` | agent | 4 partes: `objetivo` · `formato` · `tools` · `limites` → el prompt del driver |
| `role`/`who` | agent/human | rol declarado / socio dueño del gate |
| `present` | todos | `"lavish"` — emite un HTML autocontenido (gate con botones / present legible) |

**Invariantes que respeta el runner (no las rompes):** (1) cada paso deja un artefacto → resumible;
(2) cada paso tiene verify determinista → lee evidencia, no el claim; (3) el spec es datos
versionados y congelados por-run; (4) los pasos efectivos son idempotentes (o declaran
`idempotent:false`); errores permanentes (`retriable:false`) escalan sin quemar `max_iter`,
transitorios reintentan con backoff.

---

## 6. Checklist de calidad de spec (antes del gate de aprobación)

- [ ] Cada paso det referencia un `run:`/`verify:` de `steps.known()` (lo garantiza `validate_spec`).
- [ ] Cada `reads:`/`when.artifact` tiene productor upstream o está en `inputs:`.
- [ ] Ningún paso agent finge un verify de calidad sobre prosa — o tiene oráculo, o su gate es `human`.
- [ ] Los gates human de RIESGO no dependen de un `when` que pueda saltarlos con dato ausente (fail-closed).
- [ ] Los pasos efectivos no idempotentes declaran `idempotent:false`.
- [ ] `triggers:` presentes y `wf match` empata la tarea que motivó el workflow (descubrible).
- [ ] La variabilidad va por `inputs:`/`--param`, no hardcodeada (replicable / client-safe).
- [ ] Ninguna primitiva nueva colada como si existiera (frontera §2 respetada).
- [ ] `workspace wf run <nombre> --dry` → verde.

---

## 7. El catálogo de pasos det (la "API de datos" del autor)

Los pasos `det` que puedes referenciar en `run:`/`verify:`. Cada uno declara qué **produce** (las
claves de artefacto que deja, para escribir `reads:`/`when:` aguas abajo). La lista viva y autoritativa
es `steps.known()` / `steps.PRODUCES` — este catálogo se genera de ahí (`workspace wf steps` lo imprime
al día). Si el paso que necesitas NO está aquí, es una **primitiva nueva** → escala (§2), no la inventes.

*(Autoritativo en runtime: `workflows/steps/__init__.py · REGISTRY + PRODUCES`. Consúltalo con
`workspace wf steps`.)*

- `suite.green` — corre la suite de tests; verde = 0 fallos. Produce `suite_rc`, `suite_timeout_s`.
- `worktree.acquire` / `worktree.verify_acquired` / `worktree.release` — worktree con dueño desde main.
  Produce `worktree_path`, `branch`, `adopted` / `worktree_release`.
- `front.integrate` — merge a main suite-gated (no-op verde si ya mergeado). Produce `integrate_rc`,
  `integrate_noop`.
- `integrity.check` — guard de integridad del repo. Produce `integrity_flagged`, `integrity_reasons`.
- `triage.route` / `triage.verify_routed` / `triage.depth_plan` — router de hallazgos por riesgo.
  Produce `triage` / `depth_plan`.
- `evidence.artifact_exists` / `evidence.step_event` — verifies de traza: el artefacto existe / el
  paso dejó rastro N10.
- **(meta-harness)** `spec.validate` — corre `validate_spec` sobre el spec objetivo (el oráculo
  central de "el spec no está roto"). `spec.classify_frontier` — detecta si la tarea pide una
  primitiva que no existe (composición vs primitiva, §2). `spec.smoke` — `--dry` programático del
  spec objetivo (valida + planea sin ejecutar).

---

## 8. La gramática de `when:` (transición condicional) — drill-down

Un paso con `when:` corre solo si el predicado es verdadero contra los artefactos del run; falso ⇒
`skipped` (terminal, el run sigue). Un gate `human` con `when` no evaluable con certeza **PAUSA y
consulta** (fail-closed) — jamás se salta en silencio.

- **Hoja:** `{"artifact": "<clave>", "path": "a.b.0" (opcional, drill: dict→clave · list→índice),
  "op": <op>, "value": <escalar JSON, solo ops comparativas>}`.
- **Ops sin `value`:** `exists · not_exists · non_empty · empty`. **Con `value`:** `eq · ne · gt ·
  gte · lt · lte`.
- **Combinadores** (anidables ≤8): `{"all": […]}` · `{"any": […]}` · `{"not": …}`.
- **Dato ausente = fail-safe determinista:** `exists/non_empty/eq/…` → falso; `not_exists/empty` → verdadero.
- **SEGURIDAD:** el predicado son **datos, jamás código** — cero `eval`/`exec`. Op o clave fuera de
  la gramática ⇒ `validate_spec` revienta ANTES de correr nada. Esto es lo que hace client-safe que
  un agente autore `when:`.

`output_schema` (contrato de forma): `type: object|list|string|number|int|bool|any`, con
`items`/`min_items`/`max_items` (list), `required`/`optional` (object), `enum` (escalares). El runner
valida el artefacto real contra el schema ANTES del verify semántico; forma rota = fallo estructural
permanente (escala sin quemar `max_iter`).

---

*Fuente de verdad de los pipelines reales y las invariantes del runner: `workflows/MAPA.md`.
Quickstart de comandos: `workflows/README.md`. Este doc es el protocolo del AUTOR.*
