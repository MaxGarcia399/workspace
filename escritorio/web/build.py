#!/usr/bin/env python3
"""Arma la página del monito de escritorio (escritorio/web/monito.html) y su boceto.

El monito de escritorio es el MISMO de la página del navegador: no se redibuja. Este armado toma, tal cual:
  · web/front/src/10_monitos.js   (la clase Monito: silueta, ojos, gestos y estados)
  · web/front/src/20_base.js      (ayudantes de interfaz: el(), los íconos)
  · web/front/src/25_monos.js     (formas, colores y monito())
  · de web/front/src/50_chat.js: presentar() y sus reglas (RE_CEREBRITO…), lo que esconde el 🧠 y saca el menú de
    archivo: la burbuja limpia el texto con la MISMA regla que la página (modo escritorio, F0.5); y texto() con
    resumenHerr()/lineaHerr() y sus tablas: el formato de un mensaje y la línea de «lo que hizo» son los de la página
    (ronda 2, G2-a: la burbuja y el chat grande no traen otro chat, usan estas piezas)
  · de web/front/src/00_estilo.css: las variables (:root), los @keyframes, .mono, el brillo del elegido en el riel
    (.av7.on .mono) y la rayita (.ray7…), y los botones de opción (.chip)
y les suma lo propio del escritorio (escritorio/web/src/*.css y *.js, en orden por nombre).

  python3 escritorio/web/build.py            escribe escritorio/web/monito.html (lo carga la app de la Mac)
  python3 escritorio/web/build.py --check    falla si monito.html no está al día con las fuentes
  python3 escritorio/web/build.py --boceto <archivo.html> [--agentes <agentes.json>]
        el boceto animado (el mismo componente, con un escritorio de ejemplo y un recorrido); con --agentes, los
        tuyos ([{id, n, c, f, motor}], lo que da escritorio/cliente.agentes)
Stdlib."""
import json
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
FRONT = RAIZ / "web" / "front" / "src"
SRC = AQUI / "src"
BOCETO = AQUI / "boceto"
SALIDA = AQUI / "monito.html"

#: Los JS de la página, en su orden de siempre.
JS_PAGINA = ("10_monitos.js", "20_base.js", "25_monos.js")
#: Los trozos de un JS de la página que se reusan: (archivo, desde, hasta). presentar() vive entre sus reglas y la
#: tarjeta (los mismos límites que su prueba, tests/test_localhost_front).
JS_TROZOS = (("50_chat.js", "var RE_CEREBRITO", "function tarjetaExtra"),)
#: Ronda 2 (G2-a) · lo que la burbuja y el chat grande toman del chat de la página, además de presentar(): texto()
#: (`código`, **negritas**, bloques) y resumenHerr()/lineaHerr() con sus tablas (la línea de «lo que hizo»). Solo en la
#: página del monito (la capa de señalar no platica).
JS_TROZOS_CHAT = (("50_chat.js", "function texto(nodo, s)", "function esInstruccionSkill"),)
#: Las reglas de 00_estilo.css que se reusan, por su selector exacto. El brillo del elegido del riel se aplica al
#: monito del escritorio (que siempre es el elegido).
CSS_EXACTAS = (":root", ".mono", ".mono svg", ".chip", ".chip:hover", ".chip.p", ".chip.p:hover", ".chip:disabled",
               ".estado span")
CSS_PREFIJOS = ("@keyframes ", ".ray7")
BRILLO = ".av7.on .mono"
BRILLO_AQUI = ".wsm-yo .mono,.wsm-ag.on .mono"


class FaltaEnLaPagina(Exception):
    """Algo que el escritorio reusa ya no está en la página (se renombró o se quitó): hay que revisarlo, no adivinar."""


def reglas(css):
    """Las reglas de primer nivel de un CSS: [(selector, cuerpo)] en orden, sin comentarios. Un @keyframes se queda
    entero (su cuerpo trae sus propias llaves)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        sel = css[i:j].strip()
        prof, k = 1, j + 1
        while k < n and prof:
            prof += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        out.append((sel, css[j + 1:k - 1]))
        i = k
    return out


def css_de_la_pagina():
    """Lo que el escritorio toma del CSS de la página, en el orden en que la página lo trae."""
    rs = reglas((FRONT / "00_estilo.css").read_text(encoding="utf-8"))
    partes, vistos, brillo = [], set(), None
    for sel, cuerpo in rs:
        if sel in CSS_EXACTAS and sel not in vistos:
            vistos.add(sel)                       # el primer :root (el de los temas viene después y no se usa)
            partes.append("%s{%s}" % (sel, cuerpo.strip()))
        elif sel.startswith(CSS_PREFIJOS):
            partes.append("%s{%s}" % (sel, cuerpo.strip()))
        elif sel == BRILLO:
            brillo = cuerpo.strip()
    falta = [s for s in CSS_EXACTAS if s not in vistos] + ([BRILLO] if brillo is None else [])
    if falta or not any(p.startswith(".ray7") for p in partes):
        raise FaltaEnLaPagina("00_estilo.css ya no trae: %s" % ", ".join(falta or [".ray7"]))
    partes.append("%s{%s}" % (BRILLO_AQUI, brillo))
    return "\n".join(partes)


def js_de_la_pagina(mas=()):
    out = []
    for n in JS_PAGINA:
        p = FRONT / n
        if not p.exists():
            raise FaltaEnLaPagina("falta web/front/src/%s" % n)
        out.append("/* ── de la página: web/front/src/%s ── */\n%s" % (n, p.read_text(encoding="utf-8")))
    for n, desde, hasta in JS_TROZOS + tuple(mas):
        out.append("/* ── de la página: web/front/src/%s (%s…) ── */\n%s" % (n, desde, trozo(n, desde, hasta)))
    return "\n".join(out)


def trozo(nombre, desde, hasta):
    """El trozo de un JS de la página entre `desde` (incluido) y `hasta` (sin él). Si la página lo cambió, se dice."""
    p = FRONT / nombre
    src = p.read_text(encoding="utf-8") if p.exists() else ""
    i, j = src.find(desde), src.find(hasta)
    if i < 0 or j <= i:
        raise FaltaEnLaPagina("web/front/src/%s ya no trae %s … %s" % (nombre, desde, hasta))
    return src[i:j]


def propio(carpeta, ext):
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(carpeta.glob("*." + ext)))


PLANTILLA = """<!doctype html>
<html lang="es" class="{clase}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo}</title>
<!-- WORKSPACE · monito de escritorio. Generado por escritorio/web/build.py; no editar a mano. -->
<style>
{css}
</style>
</head>
<body class="{clase}">
{cuerpo}
<script>
{js}
</script>
</body>
</html>
"""


def armar():
    """La página que carga la app (fondo transparente: solo el monito y lo suyo)."""
    return PLANTILLA.format(titulo="Workspace Compañero", clase="wsm-app", cuerpo='<div class="wsm" id="wsm"></div>',
                            css=css_de_la_pagina() + "\n" + propio(SRC, "css"),
                            js=js_de_la_pagina(JS_TROZOS_CHAT) + "\n" + propio(SRC, "js"))


def armar_boceto(agentes=None):
    """El boceto: el mismo componente, encima de un escritorio de ejemplo, con sus estados y un recorrido.
    `agentes`: [{id, n, c, f, motor}] (los de tu Workspace); sin ellos, unos de ejemplo."""
    cuerpo = (BOCETO / "boceto.html").read_text(encoding="utf-8")
    previo = ""
    if agentes:
        previo = "var BOCETO_AGENTES = %s;\n" % json.dumps(agentes, ensure_ascii=False).replace("</", "<\\/")
    return PLANTILLA.format(titulo="Monitos de escritorio · boceto", clase="wsm-boceto", cuerpo=cuerpo,
                            css=css_de_la_pagina() + "\n" + propio(SRC, "css") + "\n" + propio(BOCETO, "css"),
                            js=previo + js_de_la_pagina(JS_TROZOS_CHAT) + "\n" + propio(SRC, "js") + "\n" + propio(BOCETO, "js"))


def main(argv):
    try:
        if "--boceto" in argv:
            i = argv.index("--boceto")
            if i + 1 >= len(argv):
                print("Falta el archivo: --boceto <archivo.html>")
                return 2
            destino = pathlib.Path(argv[i + 1]).expanduser()
            if destino.exists() and "--reemplazar" not in argv:
                print("Ya existe %s: los bocetos no se sobrescriben (usa otra versión)." % destino)
                return 1
            agentes = None
            if "--agentes" in argv:
                j = argv.index("--agentes")
                agentes = json.loads(pathlib.Path(argv[j + 1]).read_text(encoding="utf-8"))
            destino.write_text(armar_boceto(agentes), encoding="utf-8")
            print("escrito", destino)
            return 0
        html = armar()
    except FaltaEnLaPagina as e:
        print("No se pudo armar: %s" % e)
        return 1
    if "--check" in argv:
        actual = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
        if actual != html:
            print("escritorio/web/monito.html no está al día: corre python3 escritorio/web/build.py")
            return 1
        print("ok")
        return 0
    SALIDA.write_text(html, encoding="utf-8")
    print("escrito", SALIDA.relative_to(RAIZ), len(html), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
