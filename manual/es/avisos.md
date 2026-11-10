# Avisos de tu sistema

Tu computadora te protege: cuando un programa quiere entrar a ciertas carpetas, instalar algo
para toda la máquina o usar el micrófono, el sistema te pregunta. Workspace evita todos los avisos
que puede. Los que no se pueden evitar, te los dice **antes**, en una línea, para que sepas qué
contestar. Esta página los junta todos.

En cada uno: **qué sale**, **por qué**, **qué contestar** y **qué pasa si dices No**.

## Al instalar Workspace

| Qué sale | Por qué | Qué contestar | Si dices No |
|---|---|---|---|
| **macOS:** «Posible malware, pegado bloqueado» al pegar el comando en Terminal | macOS 26.4+ lo dice con **cualquier** comando que pegues en Terminal | Si copiaste el comando de la página de Workspace, «Pegar de todos modos» | No se instala; puedes volver a intentarlo |
| **macOS:** «El comando "git" requiere las herramientas de línea de comandos…» | Workspace se baja y se actualiza con git, que viene en las herramientas de Apple | «Instalar» y «Aceptar». Son de Apple y gratis; tardan unos minutos | No se instala hasta que las tengas |
| **Windows:** «¿Quieres permitir que esta aplicación haga cambios…?» (Git o Python) | Faltaba Git (o Python) y su instalador oficial es para toda la PC | «Sí» | No se instala hasta que tengas Git |
| **Windows Terminal:** «Advertencia: está a punto de pegar texto que contiene varias líneas» | El comando de Windows ocupa dos renglones | «Pegar de todos modos» | No pasa nada; pega cada renglón |

En Mac y Linux, Workspace se instala en `~/Workspace` y tus agentes nuevos nacen en
`~/Workspace/Cerebros`: **fuera** de Escritorio, Documentos y Descargas. Así macOS no te pide
permiso de carpetas. Si ya tenías Workspace en el Escritorio, sigue ahí y funciona igual.

## Al instalar o usar un motor (Motores)

| Qué sale | Por qué | Qué contestar | Si dices No |
|---|---|---|---|
| **Windows:** permiso de administrador la primera vez que usas **Codex** | Codex (de OpenAI) prepara su «espacio seguro» con permiso de Windows | «Sí». Si tu PC es de la empresa y no puedes, pídeselo a tu área de TI | Codex no arranca hasta que se dé el permiso |
| **Windows:** permiso de administrador al instalar **Kiro** | Su instalador oficial se instala para toda la PC | «Sí» | Kiro no se instala |
| **Windows:** permiso de administrador mientras se instala otro motor | Su instalador oficial pone algo que le falta (por ejemplo, Node.js) | «Sí» | Ese motor no se instala |
| **Windows:** «La fuente "msstore" requiere que aceptes estos acuerdos» (Copilot) | Es la tienda de programas de Windows | Escribe `Y` y Enter | Copilot no se instala |
| **macOS:** «Se agregó un elemento que se puede ejecutar en segundo plano» (Kiro) | Es parte de Kiro | Puedes dejarlo; se apaga en Ajustes → General → Ítems de inicio | Nada: Kiro sigue funcionando |
| **macOS:** «No se abrió "copilot"» o «Apple no pudo verificar…» | El motor se instaló con Homebrew y quedó en cuarentena | «Listo» (no «Mover a la papelera») y en Motores elige reinstalar | El motor no abre hasta reinstalarlo |
| **macOS:** «"Terminal" no puede modificar apps de tu Mac» | Al reparar o reinstalar un motor que vive en Aplicaciones | Ajustes → Privacidad y seguridad → Gestión de apps → activa tu terminal | La reparación no termina |
| **macOS:** el llavero pregunta por «copilot-cli» | Es Copilot leyendo su propia sesión (pasa tras actualizar Node) | Tu contraseña de la Mac y «Permitir siempre» | Copilot te pide iniciar sesión otra vez |

Workspace te dice la línea del motor **antes** de confirmar la instalación.

## Funciones opcionales

| Qué sale | Por qué | Qué contestar | Si dices No |
|---|---|---|---|
| **macOS:** «"Terminal" quiere acceder a archivos de tu carpeta Escritorio / Documentos» al **descubrir cerebros** | Solo si eliges «también Escritorio/Documentos» (tecla `e` en Descubrir): de fábrica no se busca ahí | «Permitir» deja que los encuentre | No pasa nada: busca en lo demás |
| **macOS:** «… tu carpeta Descargas» al **conectar Google** | Lee el archivo de Google que bajaste, que suele estar en Descargas | «Permitir» | No se conecta; puedes mover el archivo a otra carpeta y volver a arrastrarlo |
| **Google:** «Google no verificó esta app» | Es tu propia app, la que creaste en Google Cloud | «Avanzado» y luego «Ir a…» | Google no se conecta |
| **macOS:** «"Terminal" quiere acceder al micrófono» al **dictar por voz** | Para oírte. El audio no sale de tu Mac | «OK» | No se puede dictar |
| **macOS:** «controlar "System Events"» y Accesibilidad, solo si pediste que el dictado **pegue solo** | Para pegar el texto donde está tu cursor | «OK» y activa tu terminal en Ajustes → Privacidad y seguridad → Accesibilidad | El texto igual queda copiado: pégalo con ⌘V |
| **macOS:** «"WORKSPACE" quiere controlar "Terminal"» | La app de escritorio opcional abre Terminal | «OK» | La app no abre Terminal; usa el comando `workspace` |
| **macOS / Windows:** permiso de conexiones de red entrantes | Solo si abres Proyectos o el panel a tu red con `--host` | Permite solo redes privadas | Solo funciona en esta computadora (lo normal) |
| **Linux:** «Desbloquear el llavero de inicio de sesión» | Workspace guarda tus llaves en tu llavero | Tu contraseña de sesión | Tus llaves quedan en un archivo que solo tú puedes leer |
| **Windows:** «Se bloquearon cambios no autorizados» | Tienes encendido «Acceso controlado a carpetas» y Workspace guarda tus comandos de PowerShell en Documentos | Puedes permitirlo o no | Los comandos funcionan igual |

## Lo que Workspace ya no te pregunta

- No entra a tu Escritorio, Documentos ni Descargas por su cuenta: ni al abrir el hub ni al
  reparar un agente que se movió.
- El diagnóstico (`workspace doctor --bundle`) y el respaldo del desinstalador quedan en
  `~/Workspace/Respaldos` y se te muestran en su carpeta.
- El gateway de OpenClaw que enciende Workspace no se anuncia en tu red (por eso iTerm2 o
  VS Code ya no piden «buscar dispositivos en tu red local»).
- El dictado por voz deja el texto copiado y solo pide el micrófono; no lee lo que tenías
  copiado.
- Con el llavero de tu Mac bloqueado, Workspace no lo abre para revisar tu sesión de Copilot.

¿Te salió algo que no está aquí? Cuéntanos con el [paquete de diagnóstico](diagnostico.md).
