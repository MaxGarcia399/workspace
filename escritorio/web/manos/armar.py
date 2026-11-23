#!/usr/bin/env python3
"""Arma la capa de señalar de las manos del monito (F1: ver y señalar).

  · escritorio/web/senalar.html — la capa de señalar: una por pantalla, transparente y sin clics. Lleva el MISMO
    monito de la página (lo que toma escritorio/web/build.py de web/front/src, tal cual) más manos/senalar.{css,js}.
La tarjeta de permiso de la Mac, el ojito y el nido vacío mientras vuela son parte de la burbuja
(escritorio/web/src/12_manos.css y 25_manos.js, que arma escritorio/web/build.py en monito.html): ya no hay añadido.

  python3 escritorio/web/manos/armar.py                  la escribe
  python3 escritorio/web/manos/armar.py --check          falla si no están al día con sus fuentes
  python3 escritorio/web/manos/armar.py --demo <x.html>  el vuelo en un navegador, sobre un escritorio de ejemplo
        (para verlo y medirlo cuadro por cuadro; no lo usa la app)
Stdlib."""
import importlib.util
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
WEB = AQUI.parent
CAPA = WEB / "senalar.html"

# el armado de la burbuja, con nombre propio (sin tocar sys.path): de ahí salen el monito y el CSS de la página
_spec = importlib.util.spec_from_file_location("escritorio_web_build_manos", WEB / "build.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)


def _leer(nombre):
    return (AQUI / nombre).read_text(encoding="utf-8")


def armar_capa():
    return B.PLANTILLA.format(titulo="Monito · señalar", clase="wss-app", cuerpo='<div id="wss"></div>',
                              css=B.css_de_la_pagina() + "\n" + _leer("senalar.css"),
                              js=B.js_de_la_pagina() + "\n" + _leer("senalar.js"))


DEMO_CUERPO = """
<div class="dm-esc">
  <div class="dm-menu"><b>Hoja de cálculo</b><span>Archivo</span><span>Edición</span><span id="dmFormato">Formato</span><span>Datos</span></div>
  <section class="dm-ventana"><div class="dm-tit">Ventas_noviembre.xlsx</div>
    <div class="dm-herr"><button>Inicio</button><button>Insertar</button><button id="dmMoneda">$ Moneda</button><button>Datos</button></div>
    <div class="dm-hoja"></div>
    <button class="dm-exportar" id="dmExportar">Exportar a PDF</button>
  </section>
  <div class="dm-nido" id="dmNido"></div>
</div>
<div id="wss"></div>
"""
DEMO_CSS = """
html,body{margin:0;height:100%;background:#0c0c0e;overflow:hidden}
.dm-esc{position:fixed;inset:0;background:radial-gradient(1200px 700px at 30% 20%,#2a2340,#121216 70%);font:13px var(--sans);color:#ddd}
.dm-menu{height:28px;display:flex;gap:18px;align-items:center;padding:0 16px;background:rgba(30,30,34,.9);font-size:13px}
.dm-ventana{position:absolute;left:120px;top:80px;width:760px;height:460px;background:#1f1f23;border:1px solid #333;border-radius:12px;box-shadow:0 30px 80px rgba(0,0,0,.5)}
.dm-tit{height:36px;line-height:36px;text-align:center;color:#aaa;border-bottom:1px solid #2c2c31}
.dm-herr{display:flex;gap:8px;padding:10px 14px}.dm-herr button,.dm-exportar{background:#2b2b31;color:#ddd;border:1px solid #3a3a41;border-radius:8px;padding:6px 12px;font:inherit}
.dm-hoja{margin:4px 14px;height:300px;background:repeating-linear-gradient(#26262b 0 1px,transparent 1px 28px),repeating-linear-gradient(90deg,#26262b 0 1px,transparent 1px 110px);border:1px solid #2c2c31}
.dm-exportar{position:absolute;right:14px;bottom:12px}
.dm-nido{position:absolute;right:20px;bottom:20px;width:100px;height:118px;border-radius:28px;background:var(--rail);border:1px dashed #2c2c33}
"""
DEMO_JS = """
var EVENTOS = [];
WSS.alHost = function (op) { EVENTOS.push([Math.round(performance.now()), op]); };
function rect(id) { var r = document.getElementById(id).getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }
function nido() { var r = document.getElementById('dmNido').getBoundingClientRect(); return { x: r.left + 12, y: r.top + 8 }; }
function demo(c, f) {
  var p = [{ id: 'dmFormato', e: 'Formato → Número' }, { id: 'dmMoneda', e: 'El formato de moneda' }, { id: 'dmExportar', e: 'Y aquí lo exportas' }];
  WSS.tramo({ c: c || '#8b5cf6', f: f || 'gatito', desde: nido(), hasta: nido(),
    pasos: p.map(function (q, i) { var r = rect(q.id); r.etiqueta = q.e; r.n = i + 1; r.de = p.length; r.ms = 2400; return r; }) });
}
WSS.montar();
setTimeout(function () { demo(); }, 400);
"""


def armar_demo():
    return B.PLANTILLA.format(titulo="Monito · señalar (demo)", clase="wss-demo", cuerpo=DEMO_CUERPO,
                              css=B.css_de_la_pagina() + "\n" + _leer("senalar.css") + "\n" + DEMO_CSS,
                              js=B.js_de_la_pagina() + "\n" + _leer("senalar.js") + "\n" + DEMO_JS)


def main(argv):
    try:
        capa = armar_capa()
    except B.FaltaEnLaPagina as e:
        print("No se pudo armar: %s" % e)
        return 1
    if "--demo" in argv:
        i = argv.index("--demo")
        if i + 1 >= len(argv):
            print("Falta el archivo: --demo <archivo.html>")
            return 2
        destino = pathlib.Path(argv[i + 1]).expanduser()
        destino.write_text(armar_demo(), encoding="utf-8")
        print("escrito", destino)
        return 0
    if "--check" in argv:
        malos = [p.name for p, s in ((CAPA, capa),) if (p.read_text(encoding="utf-8") if p.exists() else "") != s]
        if malos:
            print("No están al día: %s · corre python3 escritorio/web/manos/armar.py" % ", ".join(malos))
            return 1
        print("ok")
        return 0
    CAPA.write_text(capa, encoding="utf-8")
    print("escrito", CAPA.name, len(capa), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
