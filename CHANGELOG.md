# Novedades de Workspace

Qué cambia en cada versión, contado desde tu lado de la pantalla. La versión
que tienes la ves con `workspace version` (y abajo a la derecha en el hub).
English: [CHANGELOG.en.md](CHANGELOG.en.md).

Cómo leer esto: cada versión tiene su número (`MAYOR.MENOR.PARCHE`). Un
cambio de PARCHE arregla cosas; uno de MENOR trae funciones nuevas sin romper
nada; uno de MAYOR avisa con tiempo si algo cambia de forma.

## 0.2.0 — 2026-10-13

**Un hub nuevo: el Lanzador**
- El hub es ahora una sola caja con tus agentes y, debajo, Menú,
  Personalización e Idioma. Enter entra, Esc regresa y el título te dice
  dónde estás.
- Escribe para buscar: la lista se filtra al instante y encuentra también lo
  de dentro (por ejemplo «tema»).
- ← → cambian el motor del agente apuntado (`‹ motor ›`); Tab muestra su
  información.
- La caja tiene siempre el mismo tamaño: la ventana se puede achicar hasta
  que solo quepa ella. El hub anterior y sus variantes ya no existen.
- Esc te regresa al hub desde cualquier sección (Calendario, Tono y
  Actualizaciones antes te sacaban a la terminal) y desde el menú de
  sesiones de un agente, que ahora muestra solo su nombre y sus sesiones.

**Actualizaciones con red de seguridad, y opcionales**
- Tú eliges si Workspace se actualiza solo: **automático** (como hasta ahora),
  **solo avisar** (te dice que hay versión nueva y tú decides) o **apagado**.
  Se cambia en Actualizaciones (tecla `a`) o con `workspace update --auto`.
- Antes de usar una versión nueva, Workspace comprueba que arranca en tu
  computadora. Si no arranca, vuelve solo a la que tenías y espera a que
  publiquemos un arreglo. No tienes que hacer nada.
- Si una versión nueva no te convence, `workspace update --rollback` te
  devuelve a la anterior. Tus agentes, cerebros y ajustes no se tocan.
- Los ajustes que una versión necesita hacer en tu máquina se aplican a la
  vista y quedan anotados. Si uno falla, Workspace sigue funcionando y
  `workspace doctor` te dice qué pasó y cómo seguir.
- `workspace version` muestra tu versión, tu última actualización y estas
  novedades. La versión también aparece abajo a la derecha del hub.

**Ayuda y diagnóstico**
- `workspace doctor --bundle` arma un ZIP de diagnóstico para pedir ayuda,
  con tus datos personales tachados y un LEEME que dice qué contiene.
- Nuevo manual de uso en `manual/` (español e inglés), con una tabla honesta
  de qué funciona con cada motor en cada sistema y qué datos salen de tu
  computadora.
- Plantilla para reportar problemas y canal privado para reportar fallos de
  seguridad (`SECURITY.md`).

**Comandos**
- Cada comando acepta su nombre en español y en inglés (`tono`/`tone`,
  `actualizar`/`update`…); todos los nombres de antes siguen funcionando.
- La pantalla Comandos busca con `/` y ejecuta el comando con Enter (pide
  confirmación en los delicados).
- `workspace comandos --json` le da la lista completa a tus agentes.

**Instalar, empezar y desinstalar**
- El instalador revisa tu computadora antes de tocar nada (Python, git,
  espacio, carpetas en la nube) y te dice qué arreglar, sin culparte.
- Al terminar la bienvenida ves las teclas que importan (las tuyas, si las
  cambiaste).
- Desinstalar muestra qué se borra y qué se conserva, ofrece un respaldo de
  tus ajustes (sin tus claves) y se niega a borrar carpetas que no son de
  Workspace.

**Seguridad**
- Se cerraron los fallos pendientes de una auditoría interna: la bóveda de
  claves ya no deja un archivo legible al guardar, el bus no despacha dos veces
  el mismo mensaje, la revisión de cambios de un agente detecta más tipos de
  llaves y comandos peligrosos, y una clave nunca se guarda a nombre de otra
  cuenta.

**Tono de los agentes**
- Los diales de tono son más firmes: Longitud da un tope concreto de palabras, manda sobre la forma de responder y gana si choca con otro dial. En Codex y Antigravity el tono va primero en las instrucciones de arranque.

**Temas**
- Un tema define una sola paleta y de ella salen los colores del hub, de la
  terminal y del tema dentro de Claude Code. Lo que hayas hecho a mano no se
  pisa. Nada cambia en pantalla si no eliges un tema nuevo.
- Tema nuevo **Blanco**: fondo blanco y todo lo demás en negro, el inverso
  de Mono. Los dos usan solo dos colores puros, sin grises.
- El tema y el fondo que eliges en el hub pintan también las sesiones de
  tus agentes: la barra de estado, el banner y el tema dentro de Claude
  Code. Si editaste a mano el tema de Claude Code, se respeta.

**Limpieza**
- El nombre anterior del producto desaparece de pantallas y textos; Workspace
  sigue reconociendo y migrando restos de la instalación anterior.
- La sección GitHub del hub se retira por ahora mientras la rehacemos.

## 0.1.0 — 2026-06-18

- Primera versión: hub en la terminal, agentes con su propio cerebro, motores
  intercambiables, onboarding guiado, doctor que revisa y repara, y
  actualizaciones automáticas.
