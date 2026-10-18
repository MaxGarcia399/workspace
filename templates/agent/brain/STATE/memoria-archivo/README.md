# memoria-archivo — decay de memoria (never-delete)

Cuando un core block de `STATE/MEMORY.md` excede su límite suave (N13), el excedente se ARCHIVA
aquí como `<bloque>-YYYY-MM.md` — lo hace el agente en su sesión, a la vista.
Cuando `MEMORY.md` pasa de 200 líneas, Workspace (al cerrar una sesión, sin IA) mueve lo más
viejo de su sección «Aprendido en las sesiones» a `sesiones-<año>.md`.
También viven aquí entradas viejas de `log-recent.md` cuando se rota.

El detalle nunca se borra — solo **desciende de tier** (caliente → tibia → fría). Si un tema
retoma relevancia, su contenido puede subir de vuelta a `MEMORY.md`.

*(vacío al nacer)*
