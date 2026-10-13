# Agentes y motores

## El agente

Un agente es una identidad con su **cerebro**: una carpeta de archivos Markdown que vive
**fuera** de la carpeta de Workspace. Por eso actualizar o reinstalar Workspace no toca a tus
agentes. Créalos o cárgalos desde el hub con **Agregar agente** (`g`); revísalos con
**Agentes** (`b`).

## El motor

El motor es el programa de IA que conversa con el modelo. Workspace **no reescribe** esa
parte: usa el programa oficial de cada proveedor, con **tu cuenta**.

| Motor | Programa | Cuenta | Cómo entras |
|---|---|---|---|
| **Claude Code** | `claude` (Anthropic) | tu suscripción | corre `claude` una vez y sigue el login |
| **Codex** | `codex` (OpenAI) | tu suscripción de ChatGPT | `codex login` |
| **Antigravity** | `agy` (Google) | tu cuenta Google | el propio `agy` te pide entrar |

Workspace **nunca lee ni toca** las credenciales de estos programas: el login lo hace cada uno.

## Elegir y cambiar de motor

- **Por defecto para todos:** lo eliges en el primer arranque (`workspace onboarding`).
- **Para un agente:** en el hub, apúntalo y pulsa `m` para ciclar entre los motores
  instalados. Se guarda en esta máquina.
- **Estado de cada motor:** sección **Motores** (`j`) del hub — si está instalado, si tiene sesión,
  qué puede hacer.

Cambiar de motor **no** cambia la identidad ni el cerebro del agente. Lo que no viaja es el
historial interno de cada proveedor: una conversación empezada en un motor no aparece en otro.

## No todos los motores pueden lo mismo

Claude Code es hoy el más integrado (memoria inyectada al arrancar, avisos en vivo, barra de
estado propia). Codex y Antigravity funcionan envueltos por Workspace, con algunas funciones
de menos. La lista exacta, por motor y por sistema: [Compatibilidad](compatibilidad.md).
