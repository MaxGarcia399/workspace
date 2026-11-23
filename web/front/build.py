#!/usr/bin/env python3
"""Arma web/front/index.html desde web/front/src/ (CSS y JS en orden por nombre).

El front nuevo vive como fuentes chicas en el repo; la página servida es un solo archivo, sin dependencias externas.
Uso: python3 web/front/build.py [--check]   (--check falla si index.html no está al día con las fuentes)
"""
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
SRC = AQUI / "src"
SALIDA = AQUI / "index.html"

# La página de antes sigue servida en su ruta por compatibilidad (localhost_web._ESTATICOS), pero la página nueva no la
# anuncia: ni un enlace ni un comentario (decisión del dueño, 18-nov noche; tests/test_pagina_simple.py).
PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Workspace</title>
<!-- WORKSPACE · front nuevo (un agente = una conversación). Generado por web/front/build.py desde web/front/src; no editar a mano. -->
<style>
{css}
</style>
</head>
<body>
<div class="app" id="app">
  <nav class="rail" id="rail"></nav>
  <main class="mid">
    <div class="top">
      <div class="tabs" id="tabs" role="tablist" aria-label="Sus conversaciones"></div>
      <button class="pill" id="pill" title="El agente: resumen, apariencia, tono, motor y archivos"></button>
      <div class="der"><button class="ghost" id="bSk"></button><button class="ghost" id="motor"></button></div>
    </div>
    <div class="feed" id="feed"><div class="col" id="col"></div></div>
    <div id="activa"></div>
    <div class="adjw" id="adj" style="display:none"></div>
    <div class="uso" id="uso"></div>
    <div class="box">
      <button class="cb" id="mas" title="Adjuntar o usar una skill"><svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M9 3.5v11M3.5 9h11"/></svg></button>
      <input type="file" id="fileIn" multiple hidden>
      <textarea id="ta" rows="1" placeholder="Escríbele…"></textarea>
      <button class="ajb" id="aj" style="display:none" title="Modelo y esfuerzo"></button>
      <button class="cb voz" id="voz" title="Dictar"></button>
      <button class="cb send" id="send" title="Enviar"></button>
    </div>
  </main>
  <aside class="side" id="side"><div class="in" id="sideIn"></div></aside>
</div>
<script>
{js}
</script>
</body>
</html>
"""


def armar():
    css = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SRC.glob("*.css")))
    js = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SRC.glob("*.js")))
    return PLANTILLA.replace("{css}", css).replace("{js}", js)


def main(argv):
    html = armar()
    if "--check" in argv:
        actual = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
        if actual != html:
            print("web/front/index.html no está al día: corre python3 web/front/build.py")
            return 1
        print("ok")
        return 0
    SALIDA.write_text(html, encoding="utf-8")
    print("escrito", SALIDA.relative_to(AQUI.parent.parent), len(html), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
