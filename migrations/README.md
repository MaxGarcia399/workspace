# migrations/ — ajustes que viajan con una actualización

Cada archivo `<YYYYMMDDHHMM>_<slug>.py` es un ajuste que una versión nueva
necesita hacer en la máquina del usuario (mover un archivo de estado, añadir
una clave, retirar un artefacto viejo). Lo corre `migrate.py`; cada máquina
anota lo aplicado con un sello en `<state_dir>/migrations/<id>.json`.

Por qué así: lo copiamos de Omarchy. Con clientes y equipo en versiones
distintas, el sello es la única forma de saber qué se aplicó en cada máquina
sin adivinar.

## Contrato de una migración

```python
TITLE = {"es": "Qué cambia, en palabras del usuario",
         "en": "What changes, in the user's words"}
KIND = "auto"          # "auto" (corre sola tras actualizar) | "offer" (se ofrece)

def needed(ctx):       # opcional; False → se sella "not-needed" sin correr
    return ...

def run(ctx):          # idempotente; si no puede terminar, LANZA una excepción
    ...
```

`ctx` trae `home`, `state_dir`, `root`, `dry_run`, `log(msg)` y `brains()`
(cerebros registrados que existen). Nunca construyas rutas de estado a mano:
usa `ctx.state_dir`.

## Reglas (no negociables)

1. **Idempotente.** Correrla dos veces deja lo mismo que una. Un usuario que
   llega de una versión vieja sin sellos la corre aunque ya esté aplicada.
2. **Detecta antes de tocar** (`needed`). Si la máquina no tiene lo que la
   migración arregla, no hace nada.
3. **Compatible hacia atrás (expandir → contraer).** Si mañana el usuario
   vuelve a la versión anterior (`workspace update --rollback`), esa versión
   debe seguir funcionando con lo que la migración dejó. Por eso:
   - añade claves o archivos nuevos; **no borres ni renombres** lo que una
     versión anterior lee, hasta al menos dos versiones después;
   - preferencias nuevas van en archivos nuevos o claves nuevas, nunca cambian
     el significado de una existente.
4. **Respaldo antes de lo destructivo.** Si de verdad hay que borrar o
   sobrescribir, copia primero a `<state_dir>/backups/<id>/`.
5. **Falla en voz alta.** Si algo sale mal, lanza una excepción con un mensaje
   que el usuario entienda. La cola se detiene ahí (no hay "saltar y seguir")
   y el doctor lo muestra. No dejes la máquina a medias: termina o deshaz.
6. **Rápida y sin red.** Corre al arrancar el hub. Nada de descargas ni de
   esperar al usuario. Lo lento o lo que necesita confirmación es `KIND =
   "offer"`.
7. **Las "auto" no dependen de una "offer"**: una oferta puede no aceptarse
   nunca.
8. **Nunca se edita una migración ya publicada**, salvo para arreglar una que
   FALLA en alguna máquina: la cola se detiene en ella (las siguientes no
   corren), así que el arreglo va en su mismo archivo. Donde ya se aplicó, su
   sello impide que vuelva a correr. Si estaba mal pero no falla, se escribe
   otra nueva que corrija.

## Cuándo corre

- Tras `workspace update` y tras el auto-update (proceso nuevo, con el código
  nuevo).
- Al abrir el hub, si quedó alguna pendiente (una línea visible: «✓ 1 ajuste
  de la actualización aplicado»).
- `workspace migrate` muestra el estado; `--run` las corre; `--pending`
  devuelve 1 si hay pendientes; `--offer <id>` aplica una oferta.
- En una instalación nueva, `install.py` sella todas como `first-install`.

Prueba de contrato: `tests/test_migrations_contract.py` valida nombre, `TITLE`
bilingüe, `KIND` y que cada migración sea idempotente sobre un HOME vacío.
