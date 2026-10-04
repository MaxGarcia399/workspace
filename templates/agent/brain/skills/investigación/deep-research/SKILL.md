---
name: deep-research
description: "El motor de investigación de {{AGENT_DISPLAY}} — descomponer → búsqueda en abanico → verificación adversarial → síntesis citada."
version: 1.0.0
category: investigación
tags: [investigación, web, verificación, síntesis, citas]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Deep Research — el motor de investigación de {{AGENT_DISPLAY}}

Cómo investigo de verdad un tema: el método que produce hallazgos confiables, no un resumen de los
primeros resultados de búsqueda. [[research-session]] es el flujo completo; esto es el paso
"investigar" — el músculo. Viene de fábrica con el template.

> **Principio rector:** un hallazgo sin verificación es un rumor.

## Cuándo usar
- Cuando research-session llega al paso 2 (investigar).
- Sola, cuando alguien pide "investiga X a fondo" sin necesidad del documento formal.
- Antes de afirmar en un entregable algo que no he verificado.
- NO para un dato puntual (eso es un `WebSearch` directo).

## Inputs requeridos
- [ ] La **pregunta acotada** + las **preguntas clave** que debe responder.
- [ ] ¿Tema **externo** (web), **interno** (WORKSPACE/cerebros), o **mixto**? Define las herramientas.

---

## Procedimiento

### 0. Anclar la fecha real (antes de generar cualquier query)
- **Establecer explícitamente la fecha de hoy** — del entorno (`currentDate`, o `date` del
  sistema) — ANTES de redactar queries. No confiar en "mi" noción del año.
- Usarla en toda query con componente temporal y filtrar por recencia en el triage.
- **Por qué:** sin ancla, el modelo cae al año de su training cutoff y toda la investigación
  arranca sobre resultados stale.

### 1. Descomponer (antes de buscar)
- Partir la pregunta en **3-6 sub-preguntas** o ángulos. Una búsqueda sola nunca cubre un tema.
- Por ángulo, 1-2 *queries* concretas. Variar fraseo (técnico, coloquial, por entidad, por caso
  de uso).
- Si el tema toca NUESTRO sistema, listar también los **archivos reales** a leer (WORKSPACE,
  cerebros) — no todo está en la web.

### 2. Búsqueda en abanico (fan-out)
- Lanzar las queries de los distintos ángulos — en paralelo cuando se pueda.
- **Triage:** no leer todo. Por query, las 2-4 fuentes más prometedoras por autoridad
  (doc primaria > secundaria > blog), recencia y relevancia.
- `WebFetch` las elegidas — **nunca citar a partir del snippet del buscador.**
- Para lo interno: `Read`/`Grep`/`Glob` sobre el repo/cerebro.
- **Criterio de saturación:** seguir hasta que fuentes nuevas dejen de aportar. Si un ángulo no
  satura: "evidencia insuficiente", no rellenar.

### 3. Verificación adversarial (el diferenciador — no saltarse)
Por cada **afirmación importante**:
1. **Buscar la contra** ("X no funciona", "críticas a X", "X vs Y limitaciones").
2. **Triangular:** ¿≥2 fuentes independientes (no una citando a la otra)?
3. **Etiquetar confianza:** ✅ confirmado · 🟡 plausible (con reserva explícita) · ❔ no
   encontrado/disputado (lo marco como hueco, NO lo afirmo).
4. **Cuidado con:** fechas viejas como actuales, marketing disfrazado de hallazgo, consenso
   aparente que es una sola fuente replicada.

### 4. Síntesis citada
- Organizar por las preguntas clave, no por fuente.
- **Cada afirmación importante lleva su fuente** inline. Tabla comparativa cuando hay ejes × opciones.
- Separar **hechos** (con cita) de **mi análisis/recomendación** (etiquetado como interpretación).
- Fuentes al final: título · autor/sitio · fecha · URL · fecha de acceso.

---

## Pitfalls conocidos
- **Queries con el año del training cutoff** → resultados stale desde la raíz. Paso 0.
- **Citar el snippet del buscador** sin abrir la fuente → error #1.
- **Una sola fuente = hecho.** No. Triangular o etiquetar como plausible.
- **Rellenar huecos** para que el informe "se vea completo". Un ❔ honesto vale más.
- **No leer lo interno.** Para afirmar algo de nuestro sistema hay que leer el código real.

## Verificación (antes de cerrar)
- [ ] ¿Anclé la fecha real antes de generar queries?
- [ ] ¿Cada afirmación importante tiene fuente abierta o está etiquetada como plausible?
- [ ] ¿Busqué evidencia que contradijera mis hallazgos principales?
- [ ] ¿Los huecos están marcados como huecos? · ¿Separé hechos de interpretación?

## Preferencias del equipo
*(una línea por persona del equipo o dueño — se registran con el uso)*

## Relacionado
- `skills/investigación/research-session/SKILL.md` — el flujo completo.
- Para research grande de biblioteca: delegarla a tu agente bibliotecario (si existe) vía su cola de research.
