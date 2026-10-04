# Workflows de WORKSPACE — quickstart

Un **workflow** es una lista de pasos que WORKSPACE corre en orden, uno tras otro,
verificando cada uno con evidencia real. No hay que programar nada: los pasos se
declaran en un archivo JSON guiado y WORKSPACE hace el resto.

Tres tipos de paso:

- **det** — código determinista de WORKSPACE (correr la suite, abrir un worktree, …)
- **agent** — trabajo que se le encarga a un agente, con contrato claro
- **human** — el workflow **pausa** y te pregunta a TI (un "gate")

## El flujo completo, en 4 comandos

### 1 · Crear — `workspace wf new <nombre>`

```
workspace wf new mi-flujo
```

Crea `workflows/specs/mi-flujo.json`: un esqueleto **que ya funciona**, con un
paso de cada tipo y una `note:` en cada campo explicando qué hace. Edítalo a tu
medida (cambia ids, agrega o quita pasos) y valida cada edición con:

```
workspace wf run mi-flujo --dry
```

`--dry` es un **ensayo**: valida el spec y muestra qué haría, sin ejecutar nada.
Si algo falta, el error te dice exactamente qué (y hasta sugiere el nombre
correcto si fue un typo).

### 2 · Correr — `workspace wf run <nombre>`

```
workspace wf run mi-flujo
```

Arranca la corrida ("run") y muestra el checklist de pasos. Cada run tiene un
`run-id` (aparece al inicio; lista completa: `workspace wf runs`).

### 3 · Verlo pasar — `workspace wf board` / `watch`

```
workspace wf board                  # TODAS las corridas en vivo, lado a lado
workspace wf watch <run-id>         # UNA corrida en detalle, refrescando sola
```

Ambos muestran el **paso actual** (◐) y la **duración** de cada paso — se ve
avanzar en tiempo real. Salir: `q` o Ctrl-C. Vistazo sin vivo: `workspace wf show <run-id>`.

### 4 · Decidir en los gates — aprobar o rechazar

Cuando el workflow llega a un paso **human**, pausa y espera tu decisión. Dos
caminos, el que prefieras:

**Visual (Lavish):**
```
workspace wf gate <run-id> --open
```
Abre una página en el navegador con el contexto del paso y botones
**Aprobar / Rechazar** (+ anotación opcional).

**Terminal:**
```
workspace wf decide <run-id> <paso> approve   # o reject [--note "por qué"]
```

En ambos casos la decisión queda **registrada**; aplicarla y seguir es:

```
workspace wf resume <run-id>
```

Aprobaste → el run continúa hasta el final. Rechazaste → el run termina como
`rejected` con tu anotación. Listo.

## Chuleta

| Quiero…                       | Comando                                    |
|-------------------------------|--------------------------------------------|
| crear un workflow             | `workspace wf new <nombre>`                  |
| ensayar sin ejecutar          | `workspace wf run <nombre> --dry`            |
| correrlo de verdad            | `workspace wf run <nombre>`                  |
| ver qué workflows hay         | `workspace wf list`                          |
| ver corridas recientes        | `workspace wf runs`                          |
| ver todo en vivo              | `workspace wf board`                         |
| seguir una corrida            | `workspace wf watch <run-id>`                |
| decidir un gate (visual)      | `workspace wf gate <run-id> --open`          |
| decidir un gate (terminal)    | `workspace wf decide <run-id> <paso> approve\|reject` |
| aplicar la decisión / seguir  | `workspace wf resume <run-id>`               |
| métricas de todas las corridas| `workspace wf stats`                         |

## Para profundizar

- **`MAPA.md`** — la fuente de verdad: los pipelines reales, la gramática del
  spec (`when` / `output_schema` / `produces`) y las invariantes del runner.
- **`specs/`** — los workflows disponibles; los que genera `wf new` traen la
  guía embebida.
- Los pasos **agent** corren como *stub declarado* por default (el estado lo
  dice honesto); despacharlos de verdad es opt-in: `--driver real`.
