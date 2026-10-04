# dash/ — paquete de soporte del harness

> **Nota (extracción del dashboard general):** las secciones del dashboard
> *general* cliente-facing (calendar, capture, channels, feed, kanban, matrix,
> mission_control, queue, setup_map, today, telemetry) **se extrajeron de `main`**
> y viven preservadas en la rama **`feat/dashboard`** (junto con `dashboard.html`
> y el modo NORMAL de `dashboard.py`). En `main` ya no se sirve el dashboard
> general; lo que queda de este paquete es:

- **`_common.py`** — helpers compartidos del harness (slug / frontmatter /
  read_file / inside / lectura de pendientes·sesiones·queue / inbox append…).
  **No es una sección**: lo consume `messages.py` (el bus de mensajes) y, en su
  día, las secciones generales. Se conserva porque es dependencia de código vivo.
- **`__init__.py`** — el paquete `dash` (necesario para `import dash.dev`). Sigue
  exponiendo el descubrimiento de secciones generales (`load_modules` /
  `get_routes` / `post_routes` / `js_blobs`), pero como ya no hay módulos de
  sección en este directorio, descubre el conjunto vacío.
- **`dev/`** — el **dashboard de DEV** (`workspace dev`): git-graph + switch de
  ramas + pipeline de promoción. Superficie aparte, viva en `main`. Ver
  `dash/dev/README.md`. (DEV-ONLY: se excluye de la distro a clientes.)

Para recuperar / retomar el dashboard general: `git switch feat/dashboard`.
