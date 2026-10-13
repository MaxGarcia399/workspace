# Plan de feature — <nombre>

> Template del paso `plan` de `workflows/specs/construir-feature.json`. El gate
> `contracts.plan` exige las cinco secciones de abajo (Z23, ronda Windows
> 2026-10). Lo que no aplique se dice con su motivo — no se borra la sección.

## Contrato

- Entidades y estado que toca (agentes, cerebros, motores, sesiones, settings).
- Servicios comunes que USA en vez de duplicar: `agent_state` (roster/readiness/
  revisión), `brain_resolver` (rutas de cerebro), `capabilities` (qué soporta
  OS+motor), `engine_install` (instalación oficial), `agent_schema` (formato).
- Prohibido: roster literal, nombres del equipo como default, resolver rutas a
  mano, decidir disponibilidad con `sys.platform` suelto.

## Plataformas

| Función | Windows | macOS | Linux | Cómo se prueba |
|---|---|---|---|---|
| … | soportado / no soportado (motivo) / dependencia | … | … | test / manual |

Encoding explícito (`encoding="utf-8"`) en archivos y capturas; rutas con
espacios/Unicode/drive/UNC; recursos cerrados (SQLite, handles); comando nuevo
cubre stdin cerrado / NUL / stdout redirigido y `--plan` sin efectos.

## Escenarios

- Perfil vacío (sin agentes): la vista no inventa nada y guía a cargar.
- Agente custom con nombre ajeno al equipo.
- Dependencia ausente (motor/binario/login) → estado honesto, no éxito falso.
- Datos corruptos (registro/definición/settings) → entradas válidas sobreviven.
- Cambio concurrente (otra ventana agrega/quita/reubica) → revalida antes de
  guardar o lanzar; nunca redirige la acción a otro agente.

## Migración

Si cambia formato o persistencia: versión, migración idempotente, backup y
rollback; datos locales (rutas, binarios, logins) separados de lo sincronizado.

## Evidencia

Tests por escenario (rojo antes / verde después), red de prevención
(`contracts.prevention`) y suite verdes; qué queda pendiente por OS y para el
recorrido manual. Mocks no cuentan como E2E.
