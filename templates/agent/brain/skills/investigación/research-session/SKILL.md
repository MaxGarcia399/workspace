---
name: research-session
description: "Cómo {{AGENT_DISPLAY}} corre una investigación y produce un documento citado (típicamente como sustento de trabajo de su dominio)"
version: 1.0.0
category: investigación
tags: [investigación, reporte, flujo]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Research session — el procedimiento de investigación de {{AGENT_DISPLAY}}

Lo que hago cuando mi trabajo requiere investigar un tema a fondo o cuando un socio me pide
investigar algo de mi dominio. Viene de fábrica con el template.

## 1. Acotar (antes de investigar)

- Confirmar con el socio: tema · alcance · entregable. Si está difuso, 1-3 preguntas para acotar.
  No investigar a ciegas.
- Definir las **preguntas clave** que el documento debe responder. Escribirlas; guían todo.
- ¿Esto es mío o del agente bibliotecario? **Regla:** si alimenta trabajo de MI dominio
  ({{SKILL_CATS}}) → mío. Si es biblioteca general del equipo (mercado, formación, tech amplia) →
  delegarlo a tu agente bibliotecario (si existe) vía su cola de research y registrarlo en mis pendientes.

## 2. Investigar con `deep-research`

- Usar mi skill **`deep-research`**: descompone en ángulos, busca en abanico, lee fuentes reales
  (no snippets), verifica adversarialmente, etiqueta confianza (✅🟡❔) y sintetiza citado.
- Para temas internos (WORKSPACE, cerebros): leer el código/archivos reales con las file tools.


## 3. Producir el documento

- Path: `STATE/reports/YYYY-MM-DD-<slug>.md` (crear `STATE/reports/` con el primer documento;
  versionar si se re-corre, nunca sobrescribir).
- Estructura: resumen ejecutivo · hallazgos (con confianza etiquetada) · análisis · conclusiones y
  recomendaciones · preguntas abiertas · **fuentes citadas**.

## 4. Catalogar y cerrar

- Registrar en `STATE/log-recent.md` (fecha · tema · ruta · de dónde vino).
- Si abrió pendientes (follow-ups): `STATE/PENDIENTES.md`.
- **Reportar al socio breve:** hallazgo principal + ruta del documento. El detalle vive en el
  documento, no en el mensaje.

## Notas

- Una investigación grande puede partirse en varias sesiones; dejar el documento con estado
  `en curso` y secciones pendientes marcadas.
- Si el alcance crece a mitad de camino, anotarlo y confirmar con el socio antes de expandir.

## Preferencias del equipo
*(una línea por persona del equipo o dueño — se registran con el uso)*

## Relacionado
- `skills/investigación/deep-research/SKILL.md` — el motor.
