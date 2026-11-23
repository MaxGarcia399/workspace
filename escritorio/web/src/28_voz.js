/* WORKSPACE · la voz del monito (pieza suelta): el micrófono grande de una caja de escribir.
   Hablas → el texto cae en la caja para que lo revises → TÚ lo mandas. Esta pieza nunca manda nada.
   Quien oye y transcribe es la app de la Mac (Voz.swift), en tu Mac; aquí solo se pinta.

   Cómo se coloca (una línea por caja; se puede en varias: la burbuja y el chat grande):
       WSMVoz.montar({ caja: <div de la caja>, ta: <su textarea>, nido: <el nido del monito, si hay> });
   El micrófono queda antes del botón de mandar. Sin la app (o con una app de antes, que no sabe de voz) no se pinta.

   La app le habla con: WSMVoz.app({camino, atajo}) · WSMVoz.estado({fase, frase, avance, nota}) ·
   WSMVoz.dictado({firme, volatil}) · WSMVoz.nivel(0…1).
   Y esta pieza le manda: voz_hola · voz_tocar · voz_seguir · voz_no · voz_ajustes · voz_cancelar. */
var WSMVoz = (function () {
  'use strict';
  var M = [];                 /* las cajas donde hay micrófono */
  var A = null;               /* la caja donde se está dictando (la del último toque) */
  var S = { app: null, fase: 'reposo', base: '', corte: 0, ultimo: '', mio: false, quitar: 0 };

  function host(op) {
    if (typeof WSM !== 'undefined' && WSM.alHost) { WSM.alHost(op); return; }           /* el boceto */
    try { window.webkit.messageHandlers.ws.postMessage(op); } catch (e) { }
  }
  function sabe() {
    var a = typeof WSM !== 'undefined' && WSM.s && WSM.s.app;
    return !!(a && a.capacidades && a.capacidades.indexOf('voz') >= 0);
  }
  /* lo que ya habías escrito + lo dictado, con un espacio si hace falta (lo mismo que VozLogica.unir) */
  function unir(base, dictado) {
    var d = String(dictado || '').replace(/^\s+|\s+$/g, '');
    if (!d) return base;
    if (!base) return d;
    return /[ \n]$/.test(base) ? base + d : base + ' ' + d;
  }

  function montar(o) {
    if (!o || !o.caja || !o.ta) return null;
    for (var i = 0; i < M.length; i++) if (M[i].caja === o.caja) return M[i].b;
    var m = { caja: o.caja, ta: o.ta, nido: o.nido || null };
    var b = m.b = el('button', 'wsmv-mic'); b.type = 'button'; b.title = 'Dictar'; b.setAttribute('aria-label', 'Dictar');
    b.appendChild(icono('mic'));
    var barras = el('i', 'wsmv-barras'); for (var k = 0; k < 5; k++) barras.appendChild(el('i')); b.appendChild(barras);
    b.hidden = true;
    var antes = o.antes || null;                               /* de fábrica, antes del botón de mandar de la caja */
    for (var h = 0; !antes && h < m.caja.children.length; h++) if (m.caja.children[h].classList.contains('wsm-send')) antes = m.caja.children[h];
    if (antes && antes.parentNode === m.caja) m.caja.insertBefore(b, antes); else m.caja.appendChild(b);
    /* su tarjeta (la frase de la primera vez, preparando, una nota) va justo arriba de la caja */
    m.tarjeta = el('div', 'wsmv-tarjeta'); m.tarjeta.hidden = true;
    m.caja.parentNode.insertBefore(m.tarjeta, m.caja);
    m.pie = el('div', 'wsmv-pie'); m.pie.hidden = true;
    m.caja.parentNode.insertBefore(m.pie, m.caja.nextSibling);
    if (m.nido) { m.onda = el('div', 'wsmv-onda'); for (var j = 0; j < 7; j++) m.onda.appendChild(el('i')); m.nido.appendChild(m.onda); }
    b.onclick = function () { if (S.fase === 'reposo') A = m; host({ op: 'voz_tocar' }); m.ta.focus(); };
    /* si escribes mientras dictas, lo tuyo se queda: lo dictado sigue después */
    m.ta.addEventListener('input', function () {
      if (S.mio || A !== m || (S.fase !== 'oyendo' && S.fase !== 'escribiendo')) return;
      S.base = m.ta.value; S.corte = S.ultimo.length;
    });
    /* Enter manda lo que hay (lo manda la caja, no esta pieza): el micrófono se apaga y ya no cae más texto */
    m.ta.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && A === m && (S.fase === 'oyendo' || S.fase === 'escribiendo')) {
        S.fase = 'reposo'; host({ op: 'voz_cancelar' }); pintar({ fase: 'reposo' });
      }
    }, true);
    /* la barra se cierra: el micrófono también */
    var barra = m.caja.closest ? m.caja.closest('.wsm-barra') : null;
    if (barra && typeof MutationObserver !== 'undefined') {
      new MutationObserver(function () { if (barra.hidden && A === m && S.fase !== 'reposo') host({ op: 'voz_cancelar' }); })
        .observe(barra, { attributes: true, attributeFilter: ['hidden'] });
    }
    M.push(m);
    if (!A) A = m;
    if (S.app) b.hidden = false; else saludar(0);
    return b;
  }

  /* la app tarda un momento en presentarse (WSM.app): se le pregunta por la voz cuando ya dijo que sabe */
  function saludar(n) {
    if (S.app || S.saludo) return;
    if (sabe()) { S.saludo = true; host({ op: 'voz_hola' }); return; }
    if (n < 40) setTimeout(function () { saludar(n + 1); }, 250);
  }

  /* la burbuja del monito: su caja, su textarea y su nido (30_arranque.js, tras WSM.montar) */
  function auto() {
    if (typeof WSM === 'undefined' || !WSM.piezas) return null;
    var R = WSM.piezas();
    if (!R || !R.ta || !R.ta.parentNode) return null;
    return montar({ caja: R.ta.parentNode, ta: R.ta, nido: R.nido, antes: R.send });
  }

  function app(info) {
    S.app = info && typeof info === 'object' ? info : null;
    M.forEach(function (m) { m.b.hidden = !S.app; });
    return !!S.app;
  }

  function boton(txt, op, principal) {
    var b = el('button', 'wsmv-b' + (principal ? ' p' : ''), txt); b.type = 'button';
    b.onclick = function () { host({ op: op }); if (A) A.ta.focus(); };
    return b;
  }

  function tarjeta(m, frase, botones, clase) {
    var t = m.tarjeta; t.textContent = ''; t.className = 'wsmv-tarjeta' + (clase ? ' ' + clase : '');
    if (!frase) { t.hidden = true; return; }
    t.appendChild(el('p', null, frase));
    if (botones && botones.length) { var f = el('div', 'wsmv-botones'); botones.forEach(function (x) { f.appendChild(x); }); t.appendChild(f); }
    t.hidden = false;
  }

  function pintar(o) {
    var m = A; if (!m) return;
    var f = o.fase, oye = f === 'oyendo';
    clearTimeout(S.quitar);
    M.forEach(function (x) {
      var esta = x === m;
      x.b.classList.toggle('on', esta && oye);
      x.b.classList.toggle('espera', esta && (f === 'preparando' || f === 'escribiendo'));
      x.b.title = esta && oye ? 'Terminar de dictar' : 'Dictar';
      x.b.setAttribute('aria-pressed', esta && oye ? 'true' : 'false');
      if (x.nido) x.nido.classList.toggle('wsmv-oye', oye);
      if (!esta) { x.tarjeta.hidden = true; x.pie.hidden = true; }
    });
    m.pie.hidden = !oye;
    if (oye) m.pie.textContent = 'Te escucho. Toca el micrófono' + (S.app && S.app.atajo ? ' o suelta ⌥ Espacio' : '') + ' para terminar; tú lo mandas.';
    if (f === 'aviso') tarjeta(m, o.frase, [boton('Seguir', 'voz_seguir', true), boton('Ahora no', 'voz_no')]);
    else if (f === 'apagado') tarjeta(m, o.frase, [boton('Abrir Ajustes', 'voz_ajustes', true), boton('Cerrar', 'voz_no')]);
    else if (f === 'preparando') {
      var av = +o.avance;
      if (!(av >= 0)) { tarjeta(m, null); S.barraAvance = null; }       /* casi siempre ya está listo: sin tarjeta */
      else {
        if (!S.barraAvance || m.tarjeta.hidden) {
          tarjeta(m, 'Preparando el español de tu Mac para dictar (una sola vez)…');
          var caja = el('div', 'wsmv-avance'); S.barraAvance = el('i'); caja.appendChild(S.barraAvance); m.tarjeta.appendChild(caja);
        }
        S.barraAvance.style.width = Math.round(Math.max(0.03, Math.min(1, av)) * 100) + '%';
      }
    } else if (o.nota) {
      tarjeta(m, o.nota, null, 'nota');
      S.quitar = setTimeout(function () { m.tarjeta.hidden = true; }, 9000);
    } else tarjeta(m, null);
    if (f !== 'preparando') S.barraAvance = null;
  }

  function estado(o) {
    if (!o || !o.fase) return;
    var antes = S.fase;
    if (o.fase === 'preparando' && antes === 'preparando' && +o.avance >= 0) { pintar(o); return; }
    S.fase = o.fase;
    var m = A;
    if (m && o.fase === 'oyendo' && antes !== 'oyendo') { S.base = m.ta.value; S.corte = 0; S.ultimo = ''; nivel(0); }
    pintar(o);
    if (m && o.fase === 'reposo' && (antes === 'oyendo' || antes === 'escribiendo')) {
      m.ta.focus();
      try { m.ta.selectionStart = m.ta.selectionEnd = m.ta.value.length; } catch (e) { }
    }
  }

  /* lo que va oyendo: `firme` ya no cambia, `volatil` todavía sí. Cae en la caja, después de lo que ya tenías. */
  function dictado(o) {
    var m = A;
    if (!m || !o || (S.fase !== 'oyendo' && S.fase !== 'escribiendo')) return;
    S.ultimo = String(o.firme || '') + String(o.volatil || '');
    var v = unir(S.base, S.ultimo.slice(S.corte));
    if (m.ta.value === v) return;
    S.mio = true;
    m.ta.value = v;
    try { m.ta.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) { }
    S.mio = false;
    m.ta.scrollTop = m.ta.scrollHeight;
  }

  function nivel(n) {
    var m = A; if (!m) return;
    n = Math.max(0, Math.min(1, +n || 0));
    m.b.style.setProperty('--n', n);
    if (m.onda) m.onda.style.setProperty('--n', n);
  }

  return { montar: montar, auto: auto, app: app, estado: estado, dictado: dictado, nivel: nivel, unir: unir,
    s: S, cajas: function () { return M; } };
})();
