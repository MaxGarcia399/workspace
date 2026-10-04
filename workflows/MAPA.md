# workflows/MAPA.md — mapa congelado de los pipelines de WORKSPACE

> **Fuente de verdad.** Congelado 2026-07-04 (F0, con el socio). Mapa **v1.1** (+P10 meta-harness, aditivo, 2026-07-06 — los pipelines P1-P9 no cambian); runner **v1.5** (observabilidad de corridas: evento `wf_run` + duraciones que viajan + `run_summary`, 2026-07-05 — ver changelog abajo).
> Los procesos REALES que corre WORKSPACE, escritos como pasos nombrados y testeables.
> El runner (F1) se construye contra ESTE mapa. Cambiar el mapa = versión nueva + nota al equipo.

## Cómo se lee cada paso
`entrada → acción → VERIFY (determinista) → artefacto`, con `kind`, `model_role`, `max_iter`, `on_fail`, y opcionales `idempotent` / `timeout` (v1.1), `when` / `output_schema` (v1.2 — ver §Gramática del spec), `produces` / `inputs` (v1.4 — ver §Contrato del namespace de artefactos).

**Tipos de paso:**
- `[DET]` — código determinista (la meta: verificar con Python, no con prompt)
- `[AGENTE]` — trabajo de un LLM (contrato de 4 partes: objetivo · formato · tools · límites)
- `[AD-HOC]` — hoy se improvisa cada vez = **hueco a cerrar** (migrar a `[DET]` cuando se pueda)
- `[HUMAN]` — decisión del socio

**Invariantes (no se rompen):**
1. Cada paso deja un **artefacto** → el pipeline es resumible (se reinicia a mitad sin perder).
2. Cada paso tiene un **VERIFY determinista** → código que lee la evidencia real, no el claim del agente.
3. El spec es **datos versionados y congelados** → un run empezado en vN termina en vN (deep-copy dentro del run).
4. **IDEMPOTENCIA de los pasos efectivos** (v1.1, antes implícita — ahora es LEY): "resumible" solo es verdad si re-correr un paso EFECTIVO fallido es no-op seguro. Los pasos de la biblioteca que tocan el mundo lo cumplen: `worktree.acquire` **adopta** la rama/worktree del run si ya existen (registry vivo → worktree en la rama → rama sin worktree = `add` sin `-b`); `front.integrate` es **no-op verde** si la rama ya está contenida en main (tips distintos). Un paso que NO pueda ser idempotente se declara `"idempotent": false` en el spec: el runner **no lo re-corre solo** en resume (escala al socio; el siguiente resume = aprobar) y `validate_spec` rechaza combinarlo con `on_fail: retry`.

**Taxonomía de errores (v1.1):** un resultado de paso/driver puede declarar `retriable: false` = error **PERMANENTE** (configuración/contrato: reintentar no lo arregla — p. ej. `HeadlessSecurityError`/`UnknownBackend`, que `headless.py` ya distinguía y el runner ahora **respeta**). Permanente ⇒ escalada INMEDIATA al socio sin quemar `max_iter`. Solo lo transitorio se reintenta, con **backoff exponencial + jitter** (`workflows.backoff_delay`, función pura testeada; base 0.5s, cota 30s; el sleep es inyectable — la suite jamás duerme).

**Timeout por paso (v1.1):** campo `timeout:` (segundos) en el spec. `suite.green` lo honra con corte DURO del subproceso (default 900s; al vencer el paso FALLA con detalle — el run no cuelga); `worktree.acquire` lo pasa a sus `git worktree add`; el driver real lo propaga a `run_headless`. Limitación honesta: `front.integrate` corre in-process (sus subprocesos internos llevan sus propios timeouts) — el campo no puede cortarlo desde fuera.

**Driver persistido (v1.1):** la **identidad** del driver (nombre/backend/model/timeout — jamás el callable) se guarda en `state["driver"]` cuando el run corre con driver real. `resume` sin `--driver` la **rehidrata** (el path de aprobación ya no degrada a stub en silencio); driver externo no rehidratable + sin re-inyección ⇒ los pasos agent **fallan con detalle** (permanente), y el runner se **niega a marcar DONE** si un run-con-driver terminó con pasos agent en stub (`stub_guard`). El opt-in y la postura de seguridad (tools SIEMPRE off) quedan intactos.

**Gramática del spec (v1.2) — dos primitivas aditivas** (un spec sin ellas corre exactamente igual; detalle y validadores en `workflows/grammar.py`):

- **`when:` — transición condicional.** Un paso puede declarar un predicado DECLARATIVO que el runner evalúa contra los artefactos del run justo antes de correrlo. Falso ⇒ el paso queda **`skipped`** (estado propio, distinto de ok/stub/fail; glifo `⊝` en la vista) y el run **sigue** — un paso human con `when` falso NO pausa. `skipped` es **terminal**: en resume jamás se re-evalúa (mismo run, mismos artefactos ⇒ misma decisión). En `--dry` el predicado no se evalúa (no hay artefactos reales) y el paso corre como no-op dry declarado.
  - Gramática (hoja): `{"artifact": "<clave>", "path": "a.b.0" (opcional, drill-down con puntos: dict→clave · list→índice), "op": <op>, "value": <escalar JSON, solo ops comparativas>}`.
  - Ops sin `value`: `exists · not_exists · non_empty · empty`. Ops con `value`: `eq · ne · gt · gte · lt · lte` (las numéricas exigen números en ambos lados; si no, falso). Combinadores anidables (≤8 niveles): `{"all": […]}` · `{"any": […]}` · `{"not": …}`.
  - Dato AUSENTE = fail-safe determinista: `exists/non_empty/eq/ne/gt/gte/lt/lte` → falso; `not_exists/empty` → verdadero.
  - **SEGURIDAD:** el predicado son **datos, jamás código** — cero `eval`/`exec`/imports dinámicos; la evaluación es lookup por clave + ops acotadas, pura y sin efectos. Op o clave fuera de la gramática ⇒ `validate_spec` revienta ANTES de correr nada; un string "malicioso" en artefactos o `value` solo se compara (la suite lo asserta, incluido un scan del fuente).

- **`output_schema:` — contrato de FORMA de la salida.** Un paso `agent` (o `det`) con `artifact` declarado puede exigir un esquema mínimo (stdlib puro): `type: object|list|string|number|int|bool|any`, `items`/`min_items`/`max_items` (list), `required`/`optional` (object; claves extra en el VALOR se permiten — el contrato es mínimo), `enum` (escalares). El runner valida el artefacto REAL contra el schema **antes del verify semántico**: forma rota ⇒ fallo **ESTRUCTURAL** con detalle por path (`$[2].verdict: falta la clave requerida`), `retriable: false` (contrato roto = permanente: escala al socio sin quemar `max_iter`) y el verify ni corre. Convierte "el agente dijo que lo hizo" en garantía de forma por construcción. Los stubs sin driver no se validan (no hay salida real). Artefacto commiteado como archivo (driver real) se lee y parsea JSON; texto plano solo cumple contra `type: string`.

**Consumidor real (spec `review-codigo` v3):** `fix` corre solo `when` la cola `triage.fix` no está vacía (sin CONFIRMED no hay nada que auto-arreglar); `escalar` pausa solo `when` `triage.escalar` trae algo (antes SIEMPRE pausaba, hubiera o no hallazgos — bug arreglado); `find` declara `output_schema` (lista de hallazgos `{verdict: string, …}`) — basura del agente falla estructural en `find`, jamás revienta el triage aguas abajo. v3: cada paso declara `produces:` y `triage` declara su propio `output_schema` (colas `fix`/`escalar` + `counts` garantizadas por contrato de forma).

**Contrato del namespace de artefactos (v1.4)** — la base para que un AGENTE autore specs sin reventar en runtime (detalle en `workflows/__init__.py · validate_spec/_check_artifact_refs` y `workflows/steps/__init__.py · PRODUCES`):

- **`run:`/`verify:` se RESUELVEN al cargar** contra el registry de pasos (`steps.known()`): un nombre desconocido (`worktree.acqurie`, `evidence.typo`) es **error de validación con sugerencia del cercano**, jamás sorpresa a mitad del run. (Defensa en profundidad: el camino runtime sigue poniendo el paso en rojo con detalle si un run viejo congelado referencia algo que ya no existe.)
- **`produces:` por paso** (opcional): las claves de artefacto que el paso puede dejar en el run. Un det sin él hereda el contrato del registry (`steps.PRODUCES`/`produces_of`); un agent sin él produce su `artifact:` declarado; human jamás produce. Sin nada de eso el contrato del paso es **OPACO**: aguas abajo no se puede probar nada y la validación se vuelve permisiva (decisión deliberada: compat con specs/mocks viejos — los specs de la casa SÍ declaran `produces:` completo).
- **Integridad referencial:** cada `reads:` y cada hoja `when.artifact` debe tener **productor upstream** (paso anterior cuyo contrato declara esa clave) o venir de fuera vía **`inputs:`** del spec (lista top-level de claves que llegan p. ej. por `--param`). Referencia colgante ⇒ **error al CARGAR** con sugerencia. De este recorrido cae gratis el grafo de dependencias (quién produce qué para quién) — todavía no se construyen features sobre él (p. ej. `parallel:`), a propósito.
- **`when.path` contra el `output_schema` del productor** (`grammar.path_in_schema`, trivaluado): un path PROBADAMENTE fuera del contrato (clave no declarada en un object que declara claves · índice no numérico sobre lista · path restante sobre escalar) revienta al cargar; lo que el contrato no alcanza a decidir (`any`, object sin claves, list sin items) se permite.

**El límite del verify determinista (honestidad, v1.4):** el verify es tan fuerte como su **ORÁCULO de máquina**. Donde hay oráculo real — suite (`suite.green`: exit code de los tests), git (`front.integrate`, `worktree.*`: estado verificable del repo), rutas/formas (`evidence.artifact_exists`, `output_schema`), invariantes de datos (`triage.verify_routed`) — la garantía es fuerte. Donde NO lo hay — pasos de **prosa/juicio** como `plan`, `review`, `find`: ¿el plan es bueno? ¿el review encontró lo importante? — el verify determinista solo puede comprobar **forma y existencia** (el artefacto está, tiene la estructura declarada), no calidad ni verdad. Para esos pasos **el único gate honesto es el humano** (o un verify más fuerte cuando exista, p. ej. juez con golden set). No vendemos una garantía que no existe: "verify verde" en un paso de prosa significa "la salida existe y tiene la forma pactada", punto.

**Observabilidad de corridas (v1.5, P1-D)** — el socio supervisa sin leer JSONs a mano; SOLO emisión + campos de estado (las vistas `wf show/watch/board` los consumen aparte):

- **Evento `wf_run` al rastro N10** (junto al `wf_step` de siempre; ambos `INTERNAL` en `events.py`): `phase: start` al arrancar, `phase: resume` al reanudar (con el status en que estaba el run al retomarlo) y `phase: end` al cerrar CADA pasada — done/failed/rejected/paused_human — con `ms` total y `summary` de conteos. Best-effort absoluto, como todo el rastro: `events.emit` caído jamás tumba el run.
- **Duraciones que VIAJAN:** cada paso persiste `ms` en su estado (tiempo de EJECUCIÓN acumulado entre tentativas, reloj monotónico inyectable `workflows._mono` — no cuenta backoff ni pausas human; `skipped`/fail-closed = `0` honesto) y ese `ms` va en cada evento `wf_step`. El run persiste `state["ms"]` total (reloj de PARED desde `created`, precisión de segundos — incluye pausas: eso ES lo que tardó la corrida para el socio).
- **`run_summary(state)`** — función PURA consultable (`workflows.run_summary`): `{steps, done, skipped, failed, waiting, pending, rejected, stub, attempts, ms}`. Se persiste en `state["summary"]` al cierre de cada pasada (`_close_pass`) para que dev-panel/TUI lo muestren sin recalcular.

**Métrica del progreso:** cuántos pasos `[AGENTE]`/`[AD-HOC]` migran a `[DET]`.

---

## P1 · construir-feature — flagship (primer consumidor del runner)
| # | paso | tipo | verify / gate | hueco |
|---|------|------|---------------|-------|
| 1 | plan | AGENTE | revisión del socio (a veces) | sin formato/artefacto fijo |
| 2 | rama/worktree | DET | desde main al día; registry de dueños | — |
| 3 | build | AGENTE | (falta contrato de salida) | contrato de subagente ad-hoc |
| 4 | test | DET | suite VERDE, 0 fallos + test anti-recaída | — |
| 5 | review | AGENTE | hallazgos atendidos | triage por riesgo pendiente |
| 6 | verificar-en-vivo | AD-HOC | "hace lo que debe" | sin evidencia persistida |
| 7 | integrate | DET | suite antes Y después del merge + guard | — |
| 8 | paridad (2 SOs) | HUMAN | phase-gates Fase 3 | — |
| 9 | promote/publish | DET | suite-gated; no promueve roto | — |
| 10 | cleanup | DET | auto-release de worktrees limpios; jamás --force | — |

## P2 · review-código (hoy embebido en P1; se separa)
| # | paso | tipo | verify |
|---|------|------|--------|
| 1 | find | AGENTE | emite hallazgos (CONFIRMED / PLAUSIBLE) |
| 2 | triage | AD-HOC→DET | regla dura: **PLAUSIBLE ⇒ jamás auto-fix** (router ~100 líneas = paso det nuevo) |
| 3 | fix | AGENTE | re-suite tras el fix |
| 4 | escalar | HUMAN | solo lo ambiguo/de intención llega al socio |
| 5 | profundidad por riesgo | AD-HOC | low→lint · medium→review high · high→ultra + verificar + socio |

## P3 · orquestación-nocturna (autonomía)
| # | paso | tipo | verify |
|---|------|------|--------|
| 1 | árbitro | DET | `heartbeat.decide()` — budget cap + quiet hours (ya perfecto) |
| 2 | tomar tarea | DET | cola ordenable |
| 3 | iterar | AD-HOC | falta: commit-atómico por iteración · rollback · should_fully_stop · notes.md |
| 4 | cerrar | AD-HOC | falta: morning-review con evidencia, no claims |

## P4 · destilación-memoria — **el modelo: ya ES la arquitectura**
fingerprint-skip → sanitizar (sin guard no se destila) → LLM sin tools → parsear markers → persistir gated (staging → DESTILADO.md; nunca toca MEMORY.md, la promoción es humana). Prompts congelados versionados. **Se usa como referencia de estilo; no se toca.**

## P5 · doctor — fases idempotentes por agente. Ya es la arquitectura.

## P6 · skill-loop — SessionEnd (vivo) + nightly (frío) + agregador; propuestas siempre gated. Ya explícito.

## P7 · mensajería inter-agente — bus `messages.py` (inbox → atender → done). [DET] el bus; [AD-HOC] la disciplina de atenderlo. Gap AXI (agregados, estado vacío, next-steps).

## P8 · crear-agente — HECHO harness (v1, 2026-07-06). `specs/crear-agente.json` (6 pasos: intake→gate-de-fit→crear→identidad→verificar-cerebro→aprobar) sobre `agent_admin.create` (scaffold) + `agent.verify_brain` (quality bar estructural). Protocolo del autor: `protocols/agent-creation/`. Eval semántico (golden set + juez + scorecard, `eval_runner.py`) sigue como launch gate aparte; la fase de research de dominio (FASE 1) es opcional aguas arriba.

## P9 · entregable-cliente (a nivel cerebro) — proyecto → carpeta → versionar → verificación fría → presentar → inbox. El futuro contract-review es este pipeline sobre el runner.

## P10 · META-HARNESS — el workflow que crea y modifica workflows (v1, 2026-07-06)
Dogfooding: dos workflows WORKSPACE que producen workflows WORKSPACE, corren en el mismo runner y se verifican con la misma maquinaria. El protocolo del AUTOR vive en `workflows/AUTHORING.md` (lo que los pasos `agent` leen, como `skill-creator/SKILL.md`). La **regla de oro**: los agentes autoran COMPOSICIONES de pasos del registry cerrado; JAMÁS primitivas nuevas (código `det` = ingeniería con revisión) — aplicada con paso det + gate, no con una advertencia.

**`crear-harness`** (11 pasos, v2 con CUARENTENA):
| # | paso | tipo | verify / oráculo |
|---|------|------|---------------|
| 1 | entender | AGENTE | forma (output_schema: {objetivo, pasos}) |
| 2 | clasificar-frontera | DET | `spec.classify_frontier` — ¿pide una primitiva que no existe? |
| 3 | escalar-primitiva | HUMAN | `when` needs_primitive → pausa (es código, no composición) |
| 4 | andamiar | DET | `spec.scaffold` — esqueleto válido en CUARENTENA (`specs/_pending/`), idempotente |
| 5 | componer | AGENTE | `spec.validate` como verify (sobre la copia en _pending) |
| 6 | validar-carga | DET | **`spec.validate` — el oráculo central** (registry+integridad+when+schema) |
| 7 | smoke-dry | DET | `spec.smoke` — `--dry` programático; verde SOLO si el dry terminó DONE; borra su run de ensayo |
| 8 | revisar | AGENTE | forma (checklist de calidad §6 AUTHORING) |
| 9 | aprobar-scope | HUMAN | gate N2/N3 + no-sorpresa (Lavish) — hasta aquí el spec NO es corrible |
| 10 | promover | DET | `spec.promote` — mueve _pending/ → specs/ (recién ahí es descubrible/corrible; jamás pisa un aprobado) |
| 11 | registrar | DET | `spec.discoverable` — en `wf list` + `wf match` (cierra la fuga #1) |

**Cuarentena (client-safe):** el spec autorado vive en `specs/_pending/` hasta que el gate humano aprueba — `wf run`/`list`/`match` solo ven `*.json` directos en `specs/`, así que un spec sin aprobar NO existe para el runner; rechazar el gate = jamás fue corrible.

**`modificar-harness`** (7 pasos): cargar[DET] → clasificar-cambio[AGENTE, tipo nota/estructural/preferencia] → aplicar[AGENTE, bump `version:` si estructural] → validar-carga[DET] → smoke-dry[DET] → aprobar[HUMAN] → registrar[DET]. Seguro por construcción: frozen-spec ⇒ modificar el archivo nunca afecta un run en curso.

Pasos nuevos del registry (`workflows/steps/spec.py`): `spec.scaffold · spec.classify_frontier · spec.validate · spec.smoke · spec.promote · spec.discoverable`. Sin driver, los pasos agent son STUB honesto ⇒ el meta-harness es un CHECKLIST GUIADO para un humano/agente (como una meta-skill guía su creación). Con driver real, el agente autora y el runner verifica. El protocolo del autor: `workflows/AUTHORING.md`.

---

## Aportes del socio a integrar (ver board "Arquitectura de Workflow")
- Pasos expandibles (ver sub-pasos + checks + composición).
- crear-agente como step-by-step con checklist.
- ~~**Meta-protocolo:** guía para que el agente cree nuevas pipelines/harnesses (harness dinámico, replicable, client-safe).~~ → **HECHO (P10, v1, 2026-07-06):** `crear-harness`/`modificar-harness` + `AUTHORING.md`. Fase 2 pendiente: `curar-harnesses` (podar/consolidar, como skill-curator) + eval del disparo (afinar `triggers:` contra un held-out con `match_specs`).
- Monitor de workflows activos (progreso en vivo) — en dev-panel **y en la TUI** (pipeline que se marca verde conforme avanza, como el video de referencia). *(El meta-harness lo hereda gratis: se ve avanzar en `wf board` como cualquier run.)*

## Decisiones acordadas (D0-D5, ver board)
D0 rumbo sí · D1 verify/push-guard fail-closed pero **log-only primero** · D2 secretos-desde-harness al BOOT (consenso N3) · D3 memoria sleep-time **apagada** hasta 4 candados (+ re-análisis de memoria/cerebro antes) · D4 backend-agnóstico = **contrato sí, transporte no** · D5 token-accounting **opt-in local**.

---

## Changelog del runner
- **v1.5 (2026-07-05) — observabilidad de corridas** (P1-D de la crítica; ADITIVO puro: cero cambios de semántica del runner — solo emisión de eventos + campos nuevos de duración/resumen en el estado; runs y specs viejos corren idéntico, `run_summary` sobre un run viejo simplemente reporta `ms: 0`):
  1. **`wf_run` al rastro N10** (nuevo en el vocabulario de `events.py`, `INTERNAL` en ambos motores): start al arrancar, resume al reanudar, end al cierre de cada pasada (done/failed/rejected/paused_human) con `ms` total y `summary`. Best-effort como `wf_step` — el rastro caído jamás tumba el run.
  2. **Duraciones que viajan**: `ms` de ejecución por paso (acumulado entre tentativas, monotónico inyectable) persistido en `state["steps"][i]["ms"]` e incluido en cada `wf_step`; `state["ms"]` = duración total de pared del run (desde `created`, incluye pausas).
  3. **`run_summary(state)`** (función pura) + `state["summary"]` persistido al cierre de cada pasada (`_close_pass`): conteos por estado de paso + stubs + intentos + ms — listo para dev-panel/TUI sin recalcular. Las VISTAS no se tocaron (otra rama las pule).
- **v1.4 (2026-07-05) — contrato al cargar + gates falla-cerrado + lock** (aditivo: specs viejos sin los campos nuevos siguen validando — `produces:` es opcional y su ausencia solo vuelve permisiva la integridad referencial; runs viejos intactos — `resume` usa el spec CONGELADO y jamás lo re-valida contra el contrato nuevo):
  1. **Contrato del namespace de artefactos** (P0-A — ver §arriba): `run:`/`verify:` resueltos contra el registry AL CARGAR (typo = ValueError con sugerencia); `produces:` por paso + `PRODUCES` en el registry det; integridad referencial de `reads:`/`when.artifact` (colgante = error al cargar; `inputs:` declara lo que llega de fuera); `when.path` validado contra el `output_schema` del productor. Specs de la casa actualizados: `construir-feature` **v2**, `review-codigo` **v3** (produces completo + `output_schema` propio del triage).
  2. **Gates human FALLAN-CERRADO** (P1-B): un paso human cuyo `when` no se puede evaluar con CERTEZA (dato ausente bajo op comparativa — `grammar.eval_when_certain`, lógica trivaluada) ya NO queda `skipped` en silencio: el run PAUSA y consulta al socio (`when_fail_closed`, acepta decisión approve/reject). Ops de presencia (`exists`/`non_empty`/…) siguen siendo definidas con dato ausente — el skip legítimo de `escalar` con cola vacía se conserva; los pasos no-human conservan el fail-safe v1.2. Junto con P0-A cierra el hoyo "el socio nunca es consultado": el typo muere al cargar, el residuo runtime pausa.
  3. **Lock del estado del run** (P1-C): `_run_lock` (fcntl.flock; fallback msvcrt) alrededor del read-modify-write de `<run>.json` en `record_decision` y en el arranque de `resume` — el POST del dev-panel y el CLI/loop nocturno ya no pueden pisarse (la decisión del socio jamás se pierde por last-writer-wins).
  4. **Límite del verify determinista** nombrado (P1-E — ver §arriba): fuerte con oráculo de máquina, solo forma/existencia en pasos de prosa; ahí el gate honesto es el humano.
- **v1.3 (2026-07-05) — gates con decisión + Lavish** (aditivo: sin decisión registrada y sin `present:` todo corre EXACTAMENTE igual):
  1. **Decisiones de gate** (arregla P2-11 — `resume` conflaba aprobar/rechazar): `workflows.record_decision(run, paso, approve|reject, nota)` registra la decisión del socio como DATO (`decisions[paso]`); `resume` la CONSUME — approve sigue con la anotación, reject deja el run **`rejected`** (terminal, glifo `⊗`, la anotación queda auditada). Compat: resume sin decisión = aprobar por CLI, como siempre. Vías: CLI `workspace wf decide`, POST Y1-guarded del dev-panel, o los botones del gate Lavish.
  2. **`present: "lavish"`** (opt-in por paso): el runner emite un HTML AUTOCONTENIDO look-WORKSPACE (`workflows/lavish.py`; CSS/JS inline, cero CDNs, claro/oscuro) como artefacto del run — paso human en pausa → `gate-<paso>.html` con botones **Aprobar/Rechazar + anotación** (`workspace wf gate <run> --open` lo abre); paso verde con `artifact` → `present-<paso>.html` legible. Best-effort absoluto: un HTML caído jamás toca el run. Todo dato del run va escapado; los botones no saltan Y1 (modo vivo solo mismo-origen con token; file:// → comando CLI listo para copiar).
  3. **Dev-panel**: la sección Workflows gana su ÚNICA escritura — `POST /api/dev/workflows/decide` (guard Y1 exacto, validación estricta vía `record_decision`, falla-suave, idempotente; JAMÁS avanza el run) + botones de gate en el detalle de la corrida.
- **v1.2 (2026-07-05) — gramática del spec** (aditivo: runs viejos y specs sin los campos nuevos se comportan EXACTAMENTE igual; el spec sigue congelado por-run — un run empezado en vN termina en vN):
  1. `when:` — transición condicional por paso: predicado declarativo (mini-DSL de datos, ops acotadas, **sin eval/exec** — ver §Gramática) contra los artefactos del run; falso ⇒ estado nuevo **`skipped`** (terminal, resume-safe, glifo `⊝` en la vista) y el run sigue.
  2. `output_schema` — contrato de FORMA del artefacto de un paso, validado ANTES del verify semántico; roto ⇒ fallo estructural **permanente** (escala sin quemar `max_iter`).
  3. Spec `review-codigo` **v2** los usa de verdad: bug arreglado (escalar ya no pausa con cola vacía; fix no corre sin CONFIRMED) + `find` con contrato de salida verificable. El triage además acepta el artefacto `findings` commiteado como ARCHIVO (forma del driver real), no solo como valor-dato.
- **v1.1 (2026-07-05) — endurecimiento de correctitud** (hallazgos de crítica senior; el MAPA de pipelines sigue siendo v1 y los specs corren igual — cambios aditivos, runs viejos intactos):
  1. Idempotencia de pasos efectivos EXPLÍCITA (invariante 4): acquire adopta, integrate no-op si ya mergeado, campo `idempotent: false` respetado en resume/validación.
  2. Taxonomía de errores: `retriable: false` (permanente) escala YA; transitorios con backoff exponencial + jitter.
  3. `timeout:` por paso — los subprocesos se cortan al vencer; un paso colgado FALLA, no cuelga el run.
  4. Identidad del driver persistida + rehidratada en resume; guard anti-DONE-con-stubs (`stub_guard`). Sin driver rehidratable, los pasos agent fallan honesto en vez de degradar a stub.
- **v1 (2026-07-04)** — runner F1 + driver F2 (read→execute→commit, stub honesto por default, driver real opt-in con tools OFF).

*Congelado v1 — 2026-07-04. Próximo: F1 = runner + spec de `construir-feature` (se construye pasando por el propio pipeline P1).*
