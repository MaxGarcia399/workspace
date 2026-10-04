# Memoria de sesión (por pestaña, por socio)

Un archivo por **sesión/pestaña** y por **socio**: el historial detallado de cada conversación de
trabajo con {{AGENT_DISPLAY}}. Complementa —no reemplaza— a `STATE/MEMORY.md` (memoria curada) y
`STATE/log-recent.md` (índice cronológico).

Misma convención que el resto de los agentes del equipo; el motor son los hooks genéricos de
WORKSPACE (`hooks/session_start.py` / `session_end.py`) + el `--context` de
`{{AGENT_NAME}}-dashboard.py`, que leen `$WORKSPACE_WS`.

## Árbol

```
STATE/sessions/
  README.md                          ← este archivo
  <socio>/<slug>.md                  ← journal vivo por pestaña (WARM la activa, COLD las demás)
  <socio>/<YYYY-MM>/                 ← destilados mensuales INMUTABLES (COLD)
```

## Dos capas: live journal vs destilado mensual

### Capa 1 — Live journal (`<socio>/<slug>.md`)

- Archivo WARM cuando la pestaña está activa (el hook inyecta ≤1.2k chars al boot).
- COLD el resto del tiempo (acceso bajo consulta explícita).
- Lo escribe: el agente (append fechado al cerrar trabajo significativo) + `session_end.py`
  (breadcrumb automática de red de seguridad si la sesión cierra sin captura).
- **Por socio:** solo se toca `STATE/sessions/<socio-activo>/`, nunca el de otro.

Formato del live journal:

```markdown
---
sesión: <slug>
titulo: <nombre visible de la pestaña>
socio: <socio>
workspace: <uuid>
creada: YYYY-MM-DD
actualizada: YYYY-MM-DD
estado: activa | inactiva | archivada
migrar: sí | no | pendiente
trabajo: alto | medio | bajo | por-confirmar
---

# Sesión: <titulo>

## Resumen
[1-3 líneas: qué es esta sesión y dónde va.]

## Historial
- YYYY-MM-DD — [qué pasó, decisiones, estado.]
```

### Capa 2 — Destilados mensuales (`<socio>/<YYYY-MM>/<fecha>-<slug>-<sid8>.md`)

- COLD: archivos INMUTABLES generados por el pipeline Dreaming/nightly.
- Agrupados por mes (el directorio `<YYYY-MM>/` agrupa todos los destilados del mes).
- El día de la sesión va en el nombre de archivo (no en el directorio) — facilita ordenar
  por fecha dentro del mes y locate sin abrir el directorio.
- **Jamás se editan a mano.** El campo `reemplazado_por:` es la única modificación permitida
  (la escribe el consolidador al invalidar, nunca al borrar — tipo Mem0).

Convención de nombre: `<YYYY-MM-DD>-<slug>-<sid8>.md`
  - `<YYYY-MM-DD>` — fecha de la sesión de origen
  - `<slug>` — slug de la sesión (kebab-case)
  - `<sid8>` — primeros 8 chars del session_id (provenance)

Formato del destilado (frontmatter completo — contrato E2/E3):

```markdown
---
# provenance (escribe el pipeline — no editar)
sid: 00f14635          # session_id de origen (8 chars)
prompt: dream-v1       # versión del prompt destilador
fingerprint: sha256…   # del transcript crudo

# triage (escribe el pipeline al destilar — scoring Park)
fecha: YYYY-MM-DD
importancia: 72        # 0-100; alimenta ranking BM25 × recencia × importancia (E3)
tags: [tag1, tag2]
socio: <socio>

# validez temporal (contrato E3 — invalidar, nunca borrar)
valido_desde: YYYY-MM-DD
reemplazado_por: null  # path del artefacto que lo invalida (si aplica)
                       # git guarda el historial previo
---

# Destilado — <titulo de la sesión>

[Contenido destilado ≤80 líneas. Hechos, decisiones, preferencias aprendidas.]
```

## Cómo se mantiene

- **Al abrir una pestaña**: el hook de arranque inyecta la memoria de esa sesión vía `$WORKSPACE_WS`.
- **Al cerrar trabajo significativo**: append fechado a `## Historial` + actualizar `actualizada`
  (y `estado`/`migrar`/`trabajo` si cambian). Conciso — no volcar el chat.
- **Red de seguridad**: si la sesión cierra sin captura, `session_end.py` deja breadcrumb
  automática (solo si el archivo ya existe — no auto-crea memorias).
- **Dreaming nocturno**: `dream.py` destila journals vivos → `STATE/DESTILADO.md` (staging).
  Los destilados aprobados por el humano se escriben a `<socio>/<YYYY-MM>/` como INMUTABLES.
- **Inmutabilidad de destilados**: `reemplazado_por: null` = vigente. Al invalidar, el
  consolidador rellena ese campo con el path del artefacto nuevo — el artefacto viejo queda
  en COLD pero queda excluido de resultados normales (E3 FTS5 respeta ese campo).
