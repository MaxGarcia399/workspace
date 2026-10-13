# Actualizaciones

## Qué pasa cuando Workspace se actualiza

- **Solo, al abrir un agente** (si lo dejas así; ver [Elegir cómo se actualiza](#elegir-cómo-se-actualiza)).
  Como mucho una vez cada 6 horas, Workspace revisa si hay versión nueva y la instala con la
  red de seguridad de abajo. Si no hay internet, no pasa nada.
- **Cuando tú quieras:**

  ```bash
  workspace update
  ```

  Baja la versión nueva, actualiza también los cerebros que uses con git y al final corre el
  [diagnóstico](diagnostico.md), que repara lo que haga falta. Si algo no se puede actualizar
  (sin internet, cambios tuyos a medio guardar), te avisa y sigue con lo demás.

- **Desde el hub:** sección **Actualizaciones** (`u`): revisar, reparar, actualizar y ver
  qué llegó.

## La red de seguridad

Antes de usar una versión nueva, Workspace **comprueba que arranca en tu computadora**, con
tu Python. Si no arranca:

1. vuelve solo a la versión que tenías;
2. deja esa versión **fijada** (no reintenta la misma versión rota cada 6 horas);
3. se libera solo cuando publicamos una versión más nueva.

No tienes que hacer nada. Lo verás como una línea al abrir un agente y como «versión fijada»
abajo a la derecha del hub. Si quieres reintentar igual: `workspace update --force`.

## Qué no se toca

Una actualización **solo cambia el código de Workspace**. Tus agentes, sus cerebros, tus
ajustes, atajos y temas viven fuera de esa carpeta y se conservan.

Workspace actualiza con "avance rápido": si modificaste archivos dentro de la carpeta de
Workspace, **no los pisa**; la actualización se detiene y te lo dice.

## Ajustes que trae una versión

A veces una versión necesita ajustar algo en tu máquina (por ejemplo, mover un archivo de
configuración a su lugar nuevo). Esos ajustes:

- se aplican solos tras actualizar o al abrir el hub, **a la vista** (una línea: «✓ 1 ajuste(s)
  de la actualización aplicados.»);
- quedan **anotados**, así cada ajuste corre una sola vez;
- si uno falla, Workspace **sigue funcionando**, no se aplica ningún ajuste posterior hasta
  resolverlo y `workspace doctor` te dice qué pasó;
- los cambios grandes **nunca se aplican sin preguntarte**: aparecen como «cambio opcional
  disponible» en el doctor y los aceptas con `workspace migrar --offer <id>`.

Para verlos: `workspace migrar`.

## Ver qué versión tienes y qué cambió

```bash
workspace version
```

Muestra tu versión, de cuándo es tu última actualización y las novedades de esta versión. La
versión también aparece abajo a la derecha del hub. El historial completo está en
**`CHANGELOG.md`**, en la carpeta de Workspace.

## Volver atrás

Si una versión nueva arranca pero no te convence:

```bash
workspace update --rollback
```

Te muestra a qué versión vuelves y te pide confirmación. **Solo cambia el código**: tus
agentes, cerebros y ajustes quedan como están. La versión nueva queda en pausa hasta que
publiquemos una más reciente. Los ajustes que la versión nueva ya aplicó están hechos para que
la anterior siga funcionando con ellos.

## Elegir cómo se actualiza

Las actualizaciones automáticas son **opcionales**. Hay tres modos:

| Modo | Qué hace | Sale a internet por su cuenta |
|---|---|---|
| `auto` (de inicio) | al abrir un agente instala la versión nueva, con la red de seguridad | sí, como mucho cada 6 h |
| `notify` (solo avisar) | una vez al día te dice «hay una versión nueva» y no instala nada | sí, como mucho una vez al día |
| `off` (apagadas) | no consulta nada | no |

Para cambiarlo:

- en el hub: sección **Actualizaciones** (`u`), tecla `a` (pasa de un modo al siguiente);
- en **Configuración**, apartado **Actualizaciones**;
- en la terminal: `workspace update --auto notify` (o `auto`, `off`); sin modo, te dice cuál tienes.

En los tres modos, `workspace update` instala cuando lo pides y `workspace update --rollback`
te regresa. Con `notify` u `off`, `workspace doctor` también respeta tu elección: te avisa si
hay versión nueva, pero no la instala.

Los **ajustes** de una versión (arriba) se aplican igual en los tres modos: no bajan nada de
internet, solo adaptan tu máquina al código que ya tienes.

La variable de entorno `WORKSPACE_NO_AUTOUPDATE=1` sigue funcionando y manda sobre el ajuste
(equivale a `off`).
