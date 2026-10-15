# Diagnóstico y ayuda

## El doctor

```bash
workspace doctor
```

Revisa **solo lo esencial** para que Workspace funcione y **repara** lo que puede:

- git, Python y el programa del motor que usan **tus** agentes;
- las actualizaciones (versión, ajustes pendientes o fallidos);
- **tus agentes**: que su carpeta exista, que sus *hooks* apunten a esta instalación y que
  su comando esté instalado;
- restos de una instalación anterior.

Es lo mismo que corre al final de `workspace update`. Si una fase ya está bien, la salta;
correrlo dos veces no rompe ni duplica nada. No revisa funciones opcionales (voz, terminal
partida: [Compatibilidad](compatibilidad.md)) ni cómo organizas tus cerebros, y **no tener
agentes todavía es normal**: no es un aviso.

Solo mirar, sin cambiar nada y sin salir a internet:

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
| El doctor dice que falta el CLI de un motor | instala su programa oficial y entra con tu cuenta ([Motores](motores.md)) |
| Moviste o reinstalaste Workspace y un agente falla al abrir | `workspace doctor` vuelve a apuntar sus *hooks* a esta instalación |
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
