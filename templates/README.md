# templates/ — la plantilla de un agente nuevo

Esta carpeta es lo que copia **Agregar agente** (o `python3 agent_admin.py create <nombre>`)
cuando creas un agente. No hace falta tocarla para usar Workspace.

```
templates/agent/
├── brain/              ← se copia como "<NOMBRE> - BRAIN/": el cerebro del agente
│   ├── BRAIN.md        identidad: entrada del agente (formato v2). CLAUDE.md es un puntero
│   │                   generado que la importa (`@BRAIN.md`); los demás motores llegan por
│   │                   AGENTS.md / GEMINI.md generados al lanzar.
│   ├── motores/        espacio previsto para archivos propios de un motor (vacío)
│   ├── BOOT/           alma, identidad, reglas y mapa del cerebro
│   ├── STATE/          memoria, pendientes, sesiones e inbox
│   ├── skills/         catálogo + skills para crear, mejorar y curar skills + investigación
│   ├── wiki/           conocimiento del agente (nace vacío)
│   └── adapters/       cómo opera en cada motor
└── workspace/brand/    banner, panel y barra genéricos (se usan si el agente no trae los suyos)
```

## Qué pasa al crear un agente

1. Se copia `brain/` al destino y se llenan los `{{…}}`: nombre, rol, alma, categorías de
   skills, color, alcance y fecha. Si alguno queda sin llenar, el paso final lo avisa.
2. Su definición queda en `<cerebro>/.workspace/agent.json` y viaja con el cerebro. Ahí van
   también tus dos respuestas al crearlo: `autonomy` (de entrada `brain`: libre dentro de su
   cerebro) y `skill_review` (de entrada apagada).
3. Se registra en esta máquina y se cablean sus hooks, su barra, su tema, su comando y sus
   permisos según su autonomía.
4. Lo que elegiste se cambia después en el hub: **Agentes** (elige el agente y Enter).

## Cargar un cerebro que ya tienes

**Agregar agente → cargar** (o `python3 agent_admin.py load <carpeta>`) no copia la plantilla:
respeta la definición que el cerebro ya trae y lo deja listo para usarse.

## Para quien desarrolla Workspace

- Lo común de los agentes nuevos se cambia aquí. Los agentes ya creados no cambian solos: su
  cerebro es suyo.
- `grep -rn "{{" templates/agent` lista los placeholders; `agent_admin.create` los llena.
- `templates/new_agent.py` es el instanciador de la primera versión del harness. Se conserva en
  el repo de desarrollo con su test, pero no viaja a los clientes; el camino oficial es
  `agent_admin.py create`.
