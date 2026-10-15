# Qué es Workspace

Workspace es un lugar, dentro de tu terminal, para trabajar con **varios agentes de IA**.
Cada agente tiene tres cosas:

- **Identidad** — quién es, cómo habla, qué hace.
- **Cerebro** — una carpeta de archivos de texto (Markdown) donde vive lo que sabe y recuerda.
  Es tuya: la puedes abrir, leer, editar, respaldar y llevarte.
- **Motor** — el programa de IA que realmente conversa con el modelo: Claude Code, Codex o
  Antigravity, cada uno con **tu propia cuenta**.

```
Agente = identidad + cerebro + motor
```

## Qué hace Workspace por ti

- Un **menú (el hub)** para elegir un agente y entrar con una tecla.
- Le da a cada agente su memoria al arrancar, para que no empiece de cero cada vez.
- Te deja **cambiar de motor** sin rehacer al agente.
- Se **revisa y repara solo** (`workspace doctor`) y se **actualiza solo**.
- Herramientas alrededor: calendario y tono de los agentes.

## Qué NO hace

- No es un modelo de IA ni lo reemplaza: usa el motor que tú instalas y pagas.
- No promete memoria perfecta ni que una conversación pase intacta de un proveedor a otro.
- No sube tus archivos a ningún servidor propio (ver [Privacidad](privacidad.md)).

## Estado

Workspace es **temprano**. El núcleo funciona y tiene pruebas automáticas, pero habrá
asperezas. Lo que funciona con cada motor y sistema está escrito, con honestidad, en
[Compatibilidad](compatibilidad.md).
