# Diagnóstico y ayuda

## El doctor

```bash
workspace doctor
```

Revisa Workspace **por fases** (requisitos, motores, cerebros, comandos, permisos,
capacidades de tu sistema…) y **repara** lo que puede. Si una fase ya está bien, la salta.
Correrlo dos veces no rompe ni duplica nada.

Solo mirar, sin cambiar nada y sin buscar actualizaciones (lo único que puede salir a la red
es la consulta de tu sesión de GitHub, si tienes `gh` instalado):

```bash
workspace doctor --check
```

Cada resultado sale como ✓ (bien o reparado), ⚠ (atención) o ✗ (falta algo), con la acción
que sugiere.

## Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| `workspace` no existe tras instalar | abre una **terminal nueva**; si sigue, corre de nuevo el instalador |
| El menú se ve descuadrado | agranda la ventana; en Windows usa Windows Terminal |
| Un agente no encuentra su cerebro | `workspace doctor` te dice dónde lo buscó y cómo indicarle la ruta |
| Un motor sale como "falta dependencia" | instala su programa oficial y entra con tu cuenta ([Motores](motores.md)) |
| Instalaste dentro de OneDrive | mueve Workspace fuera (p. ej. `%LOCALAPPDATA%\Workspace`); el doctor lo detecta |

## Pedir ayuda

Abre un *issue* en el repositorio de Workspace en GitHub usando la plantilla **"Reportar un
problema"**. Te pedirá:

1. Tu **versión** de Workspace y tu **sistema operativo**.
2. El **paquete de diagnóstico**:

   ```bash
   workspace doctor --bundle
   ```

   Deja `workspace-diagnostico-<fecha>.zip` en tu Escritorio (o donde digas con
   `--out <carpeta>`) e imprime la ruta. Lleva el reporte del doctor, tu versión, tu sistema,
   qué funciona con cada motor, tus agentes (nombre y motor, sin rutas) y el final de los
   registros de Workspace. **Tacha** rutas, tu usuario, el nombre de tu equipo, correos,
   tokens e IPs, y **nunca** incluye conversaciones, claves ni el contenido de tus cerebros.
   Dentro va un `LEEME.txt` que dice exactamente qué contiene y qué se tachó: ábrelo antes de
   enviarlo si quieres comprobarlo.
3. Qué hiciste, qué esperabas y qué pasó.

**¿Es un problema de seguridad?** No abras un issue público: sigue [SECURITY.md](../../SECURITY.md).
