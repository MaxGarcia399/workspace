/* ================= lo que dice el agente, listo para la burbuja =================
   La misma regla que la página (presentar, de web/front/src/50_chat.js, que el armado trae tal cual): lo que el agente
   escribe para la terminal no se ve como texto. Aquí, en chico:
     · el bloque 🧠 del cerebro se esconde (D4-a); si dice que creó o mejoró una skill, queda un chip «aprendió»;
     · el menú de archivo («📄 ruta» + «1 — abrir… 2 — revelar… 3 — seguir») es una tarjeta con «Abrir» y
       «Mostrar en Finder»; un «📄 ruta» suelto, también;
     · los separadores --- (y *** o ___) sueltos se van; lo de dentro de un bloque de código no se toca.
   Pura: sin DOM (la prueba la corre en node). */
var WSM_TEXTO = (function () {
  var SEP = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
  var ARCH = /^\s*📄\s*`?([^`]+?)`?\s*$/;
  var MENU = /^\s*(?:\d\s*[—–-]\s*(?:abrir|revelar|seguir)\b.*)$/i;
  /* el 🧠 pegado al final de un renglón (un texto que llegó sin sus saltos de línea): a su propio renglón */
  var PEGADO = /([^\n])[ \t]+(🧠[ \t]*(?:Skill creada|Skill mejorada|check[ \t]*✓)[^\n]*)$/;
  function nombreSkill(t) { var m = String(t || '').match(/`([^`]+)`/); return m ? m[1] : ''; }
  function preparar(texto, archivos) {
    var p = presentar(String(texto || '').replace(PEGADO, '$1\n$2')), lineas = p.cuerpo.split('\n'), cuerpo = [], codigo = false;
    var out = { cuerpo: '', aprendio: [], archivos: [] }, vistos = {};
    function sumar(ruta, titulo) {
      ruta = String(ruta || '').replace(/^`|`$/g, '').trim();
      if (!ruta || vistos[ruta] || out.archivos.length >= 6) return;
      vistos[ruta] = 1; out.archivos.push({ ruta: ruta, titulo: titulo || '' });
    }
    for (var i = 0; i < lineas.length; i++) {
      var l = lineas[i];
      if (/^\s*```/.test(l)) { codigo = !codigo; cuerpo.push(l); continue; }
      if (!codigo) {
        if (SEP.test(l) || MENU.test(l)) continue;
        var ma = l.match(ARCH);
        if (ma) { sumar(ma[1]); continue; }
      }
      cuerpo.push(l);
    }
    p.extras.forEach(function (x) {
      if (x.tipo === 'archivo') sumar(x.ruta, x.titulo);
      else if (x.tipo === 'skill-nueva' || x.tipo === 'skill-mejor') out.aprendio.push({ tipo: x.tipo, nombre: nombreSkill(x.texto), texto: x.texto || '' });
      /* 'cerebrito' (otro cierre 🧠 del cerebro): en la burbuja no se ve */
    });
    (archivos || []).forEach(function (a) { if (a && a.ruta) sumar(a.ruta, a.titulo); });
    out.cuerpo = cuerpo.join('\n').replace(/\n{3,}/g, '\n\n').trim();
    return out;
  }
  return { preparar: preparar };
})();
