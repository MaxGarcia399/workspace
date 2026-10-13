# Compatibilidad: motor × sistema operativo

Qué funciona hoy, con qué motor y en qué sistema. Si algo no está aquí como "funciona",
no lo prometemos.

<!-- Fuente: capabilities.py (estados y reglas por OS) + CAPABILITIES de engines/*.py.
Tablas verificadas contra el código; tests/test_manual_compat.py recalcula cada celda desde
capabilities.py y falla si la tabla queda desactualizada (aquí o en ../en/compatibility.md). -->

## Cómo verlo en tu máquina

La tabla de abajo es general. Lo que vale **en tu equipo**, con lo que tienes instalado, lo
dice el diagnóstico, sin cambiar nada:

```bash
workspace doctor --check
```

Busca la fase **"Capacidades efectivas (OS + motor + dependencias)"**. Cada función sale con
uno de estos estados:

| Estado | Significa |
|---|---|
| **disponible** | funciona aquí, con lo que tienes |
| **no soportado** | no existe en este sistema o en este motor (se dice por qué) |
| **falta dependencia** | existiría, pero falta instalar algo (se dice qué y cómo) |
| **sin verificar** | Workspace no puede comprobarlo sin ejecutar o iniciar sesión; no lo inventa |

## Por motor

Vale para macOS, Linux y Windows, salvo donde se indica.

| Función | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Abrir el agente desde el hub | ✅ | ✅ (envuelto) | ✅ (envuelto) |
| El agente arranca con su memoria | ✅ automático | ✅ vía un `AGENTS.md` que Workspace genera en el cerebro | ✅ vía un `GEMINI.md` que Workspace genera en el cerebro |
| Conectores MCP | ✅ | ✅ (configuración del propio Codex) | ✅ |
| Avisos de sesión (*hooks*: guardar memoria al cerrar, etc.) | ✅ | ❌ | ❌ |
| Retomar sesiones desde las pestañas de Workspace | ✅ | ✅ | ✅ |
| Estado en vivo del agente en el hub | ✅ | ❌ | ❌ |
| Tareas sin ventana (evals, workflows) | ✅ | ✅ | ❌ |

✅ funciona · ❌ no disponible · ❔ sin verificar

Si el programa del motor no está instalado (o no está en el PATH), las funciones que dependen
de él salen como **falta dependencia**, y el diagnóstico te dice que instales su programa
oficial ([Motores](motores.md)).

## Por sistema (funciones de Workspace)

| Función | macOS | Linux | Windows |
|---|---|---|---|
| Dictado por voz (local) | ✅ si instalas whisper.cpp, su modelo y ffmpeg o sox | ❌ por ahora | ❌ por ahora |
| Terminal partida (chat + tablero) | ✅ con tmux o herdr | ✅ con tmux o herdr | ❌ abre la sesión sencilla |
| Controles del panel lateral | ✅ dentro de la terminal partida | ✅ dentro de la terminal partida | solo lectura |

## Límites actuales

- **"Tú eliges el motor" es verdad a medias hoy.** Los tres motores abren agentes con su
  memoria, pero Claude Code tiene más integración, y parte de la configuración local todavía
  vive en `~/.claude/workspace/` aunque no uses Claude Code.
- **Cambiar de motor no traslada conversaciones**: el cerebro sí viaja; el historial interno
  de cada proveedor, no.
