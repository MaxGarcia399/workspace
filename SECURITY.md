# Security policy · Política de seguridad

<!-- TODO(dueño): confirmar canal. (No se escribe el nombre corto del dueño aquí: el gate
de fuga de make-dist.sh aborta el build con él.) Requiere activar "Private vulnerability reporting" en
GitHub → Settings → Code security del repo público (MaxGarcia399/workspace). Si se prefiere
otro canal (correo dedicado), reemplazar la sección "How to report" en ambos idiomas. -->

## English

### How to report

**Please don't open a public issue for security problems.** Report them privately through
GitHub:

1. Go to the repository's **Security** tab → **Report a vulnerability**
   (<https://github.com/MaxGarcia399/workspace/security/advisories/new>).
2. Describe what you found, how to reproduce it, and what an attacker could do with it.
3. Include your Workspace version and operating system. If you attach a diagnostic bundle
   (`workspace doctor --bundle`, coming soon), check it first: it is designed to leave out
   secrets and personal data, but you decide what you share.

Only the maintainers can see a private report.

### What to expect

Workspace is an early, small project maintained by one person, so we can't promise fixed
response times. We will acknowledge your report, keep you posted, and credit you in the
changelog when the fix ships (unless you prefer not to be named).

### Scope

In scope: the code in this repository — the installer, the `workspace` command, hooks,
engine adapters, and anything that could leak credentials or files, or run code you didn't
approve.

Out of scope: the engines themselves (Claude Code, Codex, Antigravity) and their accounts —
report those to their vendors.

### Supported versions

Only the latest version on `main` receives fixes. `workspace update` gets you there.

## Español

### Cómo reportar

**Por favor no abras un issue público para problemas de seguridad.** Repórtalos en privado
por GitHub:

1. Ve a la pestaña **Security** del repositorio → **Report a vulnerability**
   (<https://github.com/MaxGarcia399/workspace/security/advisories/new>).
2. Describe qué encontraste, cómo reproducirlo y qué podría hacer un atacante con ello.
3. Incluye tu versión de Workspace y tu sistema operativo. Si adjuntas un paquete de
   diagnóstico (`workspace doctor --bundle`, próximamente), revísalo antes: está pensado para
   dejar fuera secretos y datos personales, pero tú decides qué compartes.

Solo los mantenedores ven un reporte privado.

### Qué esperar

Workspace es un proyecto temprano y pequeño, mantenido por una persona, así que no podemos
prometer tiempos fijos de respuesta. Confirmaremos que recibimos tu reporte, te mantendremos
al tanto y te daremos crédito en el changelog cuando salga el arreglo (salvo que prefieras no
aparecer).

### Alcance

Dentro: el código de este repositorio — el instalador, el comando `workspace`, los hooks, los
adaptadores de motor y todo lo que pueda filtrar credenciales o archivos, o ejecutar código
que no aprobaste.

Fuera: los motores mismos (Claude Code, Codex, Antigravity) y sus cuentas — repórtalos a sus
proveedores.

### Versiones con soporte

Solo la última versión en `main` recibe arreglos. `workspace update` te lleva ahí.
