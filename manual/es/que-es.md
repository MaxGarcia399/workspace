# Qué es Workspace

Workspace es un lugar, dentro de tu terminal, para trabajar con **varios agentes de IA**.
Cada agente tiene tres cosas:

- **Identidad** — quién es, cómo habla, qué hace.
- **Cerebro** — una carpeta de archivos de texto (Markdown) donde vive lo que sabe y recuerda.
  Es tuya: la puedes abrir, leer, editar, respaldar y llevarte.
- **Motor** — el programa de IA que realmente conversa con el modelo: Claude Code, Codex,
  Antigravity, OpenCode, OpenClaw, Hermes, Kiro, GitHub Copilot o Cursor, cada uno con **tu
  propia cuenta**.

```
Agente = identidad + cerebro + motor
```

## Qué hace Workspace por ti

- **Configura y abre tus motores oficiales**, con tu cuenta. El motor sigue siendo el que
  habla con el modelo.
- Un **menú (el hub)** para elegir un agente y entrar con una tecla.
- Le da a cada agente su memoria al arrancar, para que no empiece de cero cada vez.
- Te deja **cambiar de motor** sin rehacer al agente.
- Se **revisa y repara solo** (`workspace doctor`) y se **actualiza solo**.
- Herramientas alrededor: calendario y tono de los agentes.

## Qué NO hace

- No es un modelo de IA ni lo reemplaza: usa el motor que tú instalas y pagas.
- No promete memoria perfecta ni que una conversación pase intacta de un proveedor a otro.
- No sube tus archivos a ningún servidor propio (ver [Privacidad](privacidad.md)).
- No está afiliado a las empresas de los motores ni cuenta con su respaldo (ver
  [Agentes y motores](motores.md#el-motor)).

## Estado

Workspace es **temprano**. El núcleo funciona y tiene pruebas automáticas, pero habrá
asperezas. Lo que funciona con cada motor y sistema está escrito, con honestidad, en
[Compatibilidad](compatibilidad.md).
