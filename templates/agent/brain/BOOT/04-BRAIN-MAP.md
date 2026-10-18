# Mapa del cerebro

Mi cerebro vive en **capas de acceso** (HOT/WARM/COLD), no solo carpetas. La capa determina
cuándo se carga algo: HOT = siempre al boot (cuesta tokens cada arranque — por eso tiene tope
duro); WARM = JIT cuando la tarea lo pide; COLD = solo bajo consulta explícita.

## Árbol por capas

```
{{AGENT_UPPER}} - BRAIN/
│
│  ── HOT (entra al boot SIEMPRE; suma ≤~26k chars ≈ 6.5k tokens) ──
├── BRAIN.md               Identidad: entry point — boot order + punteros. Tope ≤3k chars.
├── CLAUDE.md              Puntero GENERADO para Claude Code (importa BRAIN.md). No editar arriba de su marca de fin.
├── BOOT/                  Identidad inmutable. Tope 12k chars/archivo. HOT completo.
│   ├── 00-SOUL.md         Personalidad, carácter, por qué existo.
│   ├── 01-IDENTITY.md     Tarjeta básica.
│   ├── 02-TEAM.md         Socios + otros agentes + reglas multi-usuario.
│   ├── 03-RULES.md        Security N1/N2/N3 + reglas inmutables + scope.
│   └── 04-BRAIN-MAP.md    Este archivo: mapa de capas + tabla STATE/ + retrieval.
├── STATE/                 Corazón operacional.
│   ├── brain-version.md   HOT · versión + changelog ROTADO. Tope 2.5k chars.
│   ├── MEMORY.md          HOT · memoria curada (core blocks N13). Tope DURO 13.5k chars.
│   ├── INDEX.md           HOT ★E2★ · contrato de retrieval: 1 línea→path. Tope 100 líneas.
│   └── users/<socio>.md   HOT (solo el socio activo) · perfil de trato. Tope 2k chars c/u.
├── skills/INDEX-LITE.md   HOT · ≤300 tokens: categorías + conteo + regla de carga.
│
│  ── WARM (JIT — vía regla explícita o lectura del INDEX.md) ──
├── STATE/PENDIENTES.md    WARM · trabajo activo. Tope 6.6k chars.
├── STATE/MILESTONES.md    WARM · hitos. Leer al discutir fechas. Tope 4k chars.
├── STATE/log-recent.md    WARM · bitácora. Leer SOLO si brain-version reporta cambios ≤7d.
│                          Tope 4k chars; lo viejo lo muevo yo a STATE/log-archive/ (nunca se borra).
├── STATE/inbox/           WARM · bus append-only. Leer al arrancar si hay mensajes.
├── STATE/sessions/<socio>/<slug>.md  WARM la pestaña activa: al abrir llega su paquete (resumen +
│                          Vigente + notas nuevas + maleta). Solo escribo con `workspace memoria`.
├── STATE/sessions/<socio>/checkpoints/ · maleta/  WARM · resumen de cada pestaña · lo último de
│                          cada motor (los escribe Workspace; entran al paquete).
├── skills/README.md       WARM · catálogo completo. Leer al buscar skill aplicable.
├── skills/<cat>/<skill>/SKILL.md  WARM · JIT al detectar tarea aplicable.
├── wiki/                  WARM/COLD · conocimiento propio on-demand. NUNCA cargar entero.
├── adapters/              WARM · cómo opero por runtime.
└── motores/               Espacio propio de cada motor: `motores/claude-code/memoria/` = memoria
                           automática de Claude Code (la carga él). Ver motores/README.md.
│
│  ── COLD (archival; solo bajo consulta explícita o grep/FTS5) ──
├── STATE/sessions/<socio>/<slug>.md  COLD las sesiones no-activas.
├── STATE/sessions/<socio>/archivo/   COLD · notas viejas de cada pestaña, por mes (nada se borra).
├── STATE/memoria-archivo/ COLD · overflow de MEMORY (decay, never-delete).
├── STATE/log-archive/     COLD · rotación de log-recent + changelogs viejos.
│
│  ── DERIVADO (regenerable; gitignored; per-máquina; jamás fuente de verdad) ──
└── STATE/boot-lite.md     Digest ≤4k de BOOT/ (boot_lite.py). Motor #2 / boots baratos.
```

## STATE/ — contrato completo por archivo

| Archivo / carpeta | Qué tiene | Capa | Tope |
|---|---|---|---|
| `STATE/brain-version.md` | Versión + changelog. **Primero al boot.** | HOT | 2.5k chars |
| `STATE/MEMORY.md` | Memoria curada largo plazo. Core blocks N13 + «Aprendido en las sesiones» (la llena Workspace). | HOT | 13.5k chars |
| `STATE/INDEX.md` | Índice de retrieval: 1 línea→path. | HOT | 100 líneas |
| `STATE/users/<socio>.md` | Perfil de trato del socio activo. | HOT | 2k chars c/u |
| `STATE/PENDIENTES.md` | Trabajo activo. | WARM | 6.6k chars |
| `STATE/log-recent.md` | Bitácora — solo si cambios ≤7 días. | WARM | 4k chars |
| `STATE/MILESTONES.md` | Hitos. | WARM | 4k chars |
| `STATE/inbox/` | Bus append-only. Leer al arrancar si hay mensajes. | WARM | — |
| `STATE/sessions/<socio>/` | Una ficha por pestaña: Resumen + Vigente + Historial (`workspace memoria nota`). | WARM activa · COLD el resto | 30 notas u 8 KB (luego compacta) |
| `STATE/sessions/<socio>/checkpoints/` · `maleta/` | Resumen de cada pestaña · lo último de cada motor. | WARM | — |
| `STATE/sessions/<socio>/archivo/` | Notas viejas que salen de la ficha al compactar. | COLD | ilimitado |
| `STATE/memoria-archivo/` | Overflow de MEMORY (decay, never-delete). | COLD | ilimitado |
| `STATE/log-archive/` | Rotación de bitácoras viejas y changelogs. | COLD | ilimitado |
| `STATE/boot-lite.md` | Digest BOOT/ (boot_lite.py — gitignored). | DERIVADO | 4k chars |

## skills/ — catálogo en dos niveles

- `skills/INDEX-LITE.md` — índice ligero (HOT): categorías + conteo + regla de carga.
- `skills/README.md` — catálogo completo (WARM): tabla por categoría.
- Categorías de {{AGENT_DISPLAY}}: **{{SKILL_CATS}}** + `meta/` (el sistema de skills) +
  `investigación/` (el músculo de research).
- `skills/_archive/` — lo archivado y las copias previas (nada se borra). Ninguna skill espera aprobación.

## Cómo busco (retrieval por capas)

1. **INDEX.md ya está en contexto** (HOT) → decidir → 1 `Read`. Es el camino rápido.
2. **Catálogos WARM:** `skills/INDEX-LITE.md`, `STATE/log-recent.md`, `wiki/index.md`.
3. **grep** sobre el cerebro relevante: `grep -r "término" STATE/` o `wiki/`.
4. **FTS5 (E3):** `~/.claude/workspace/index/<cerebro>.db` — cubre las fichas de las pestañas
   y su `archivo/` + wiki + memoria-archivo + log-archive + inbox-consumido. Regenerable
   (`--reindex`). **No disponible en E1/E2 — el fallback es siempre grep.**
5. Si no encuentro: lo digo — no invento.

## Lo que NO vive aquí (pero leo para trabajar)

| Recurso | Dónde | Mi acceso |
|---|---|---|
| El harness | `~/Desktop/WORKSPACE/` | Leer N1 · tocar = tiers de BOOT/03 |
| Cerebro principal del equipo (wiki compartido) | otro cerebro del equipo | **Solo lectura.** Escrituras → su `STATE/inbox/` |
| Cerebro del agente bibliotecario (biblioteca) | otro cerebro del equipo | **Solo lectura** + encargos vía su cola de research |
| Cerebro del agente de seguridad (reportes de salud) | otro cerebro del equipo | **Solo lectura.** Escrituras → su `STATE/inbox/` |
| Mi registro/brand en el harness | `WORKSPACE/agents/{{AGENT_NAME}}/` | Es código de WORKSPACE — tiers de BOOT/03 |
