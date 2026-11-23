# Avisos de terceros · manos del monito de escritorio (F1: ver y señalar)

Lo que las manos del monito toman de proyectos abiertos. Todos con licencia MIT.

| Proyecto | Licencia | Cómo se usa |
|---|---|---|
| [AXorcist](https://github.com/openclaw/AXorcist) · © 2025 Peter Steinberger | MIT | **Dependencia** de SwiftPM, fijada a 0.2.3 (`escritorio/mac/Package.swift`). La app la usa para la accesibilidad: la app y la ventana de enfrente, el elemento con foco, la selección, la URL del navegador, lo que hay bajo el ratón, la barra de menú y los permisos. El recorrido del árbol (`leer_ventana`) es nuestro, con atributos pedidos de un jalón. |
| [Clicky](https://github.com/farzaa/clicky) · © 2026 Farza | MIT | **Idea**, sin copiar código: señalar con una capa transparente por pantalla que no toma clics, el vuelo en arco (curva de Bézier cuadrática con el cuerpo que crece a la mitad) y convertir las coordenadas de la foto a las de la pantalla. Aquí el vuelo lo hace el mismo monito de la página (`escritorio/web/manos/senalar.js`). |
| [OpenClicky](https://github.com/jasonkneen/openclicky) · © 2026 Jason Kneen | MIT | **Idea**, sin copiar código: señalar con una etiqueta corta junto al objetivo, varios pasos en orden, y la regla de las guías paso a paso (señalar solo lo que se ve y es el siguiente paso; si depende de lo que haga la persona, esperar y volver a mirar). Su puente local usa un puerto fijo sin ficha: aquí es puerto al azar, solo 127.0.0.1 y con ficha. No se revisó ni se usa su «runtime» empaquetado. |
| [Peekaboo](https://github.com/openclaw/Peekaboo) · © 2025 Peter Steinberger | MIT | **Idea**, sin copiar código: los elementos de la ventana numerados con su lugar para señalarlos por número, la lista de roles que se pueden tocar y la foto más su texto por OCR. |

Lo demás es de Apple (AppKit, WebKit, ScreenCaptureKit, Vision, ImageIO, Network) o de Workspace.

## Licencia MIT (la misma para los cuatro, con su aviso de copyright de arriba)

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
