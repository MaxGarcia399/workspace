# Reglas de revisión de Workspace

Escribe los comentarios en español. Marca como hallazgo todo cambio que rompa una de estas reglas.
Explicación completa: `runbooks/reglas-de-codigo.md`.

1. **Archivos compartidos.** Un archivo que pueden escribir dos procesos se modifica bajo un
   candado entre procesos. El temporal es único por proceso y se instala con `os.replace`. No se
   aceptan copias nuevas de `_atomic_write`.
2. **Ilegible no es vacío.** Si un archivo falla al leerse o interpretarse, se aparta con otro
   nombre y se avisa; nunca se guarda encima. Se lee con `utf-8-sig`.
3. **Éxito comprobado.** Un mensaje de éxito («✓», «ok», «listo», `ok: True`) exige comprobar
   antes el efecto real y el código de salida. Las pruebas cubren el camino de falla.
4. **Varias pestañas, sesiones y máquinas.** Lo que se crea, se libera o se ata lleva el
   identificador de su sesión dueña. Lo que viaja con el cerebro se decide con datos del cerebro,
   no de la máquina.
5. **Una implementación.** Si la lógica ya existe en otro módulo, se reutiliza. Un arreglo en una
   copia se aplica a todas.
6. **Texto ajeno.** Nada de `shell=True`, comandos armados con texto ni código generado con
   `replace`. Se usan listas de argumentos y `json.dumps`/`repr`. Son entrada no confiable los
   títulos, los nombres de ramas o agentes, los archivos sincronizados y la salida del modelo.
7. **Windows.**
   - Los programas de npm se lanzan resolviendo la ruta con `shutil.which`.
   - El texto largo va por stdin.
   - Los procesos de fondo usan `CREATE_NO_WINDOW`.
   - No se usa `os.kill(pid, 0)` ni `os.execvp`.
   - La codificación es explícita y la salida, UTF-8.
8. **Pertenencia en la interfaz.** Cada guardado o respuesta asíncrona va contra el id del elemento
   que la originó. Nunca se repinta el campo con foco.
9. **Secretos.** Nunca se exportan a `os.environ`, ni van en argumentos de comando o en registros.
   Las conexiones que llevan una llave verifican TLS y no siguen redirecciones.
10. **Mac y Python 3.9.**
    - El código corre en Python 3.9.6: nada de `match`, `zip(strict=)` ni `X | Y` evaluado; en
      argparse con posicional `nargs="*"`, `parse_intermixed_args`.
    - Las rutas se comparan con `os.path.realpath` (`/tmp` → `/private/tmp`).
    - No se depende de `HOSTNAME` ni de `COLORTERM`.
    - Un pid guardado se verifica (comando u hora de inicio) antes de darlo por vivo o matarlo.
    - Una prueba de una sola plataforma lleva `skipUnless`; las E2E cubren ConPTY y pty.
    - Las pruebas que ejecutan scripts de Workspace usan un HOME temporal.
