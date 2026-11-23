/* ================= la caja: adjuntos y dictado ================= */
/* adjuntos: se suben a su cerebro (STATE/adjuntos/…) y su ruta viaja con el mensaje */
var ADJ = [];
function pintarAdjuntos() {
  var w = $('#adj'); w.textContent = '';
  ADJ.forEach(function (x) {
    var c = el('span', 'adjc' + (x.mal ? ' mal' : x.ruta ? '' : ' sub')); c.appendChild(svg('doc')); c.appendChild(el('span', null, x.nombre));
    c.title = x.mal || x.ruta || 'subiendo…';
    var q = el('button', 'adjx'); q.appendChild(icono('x')); q.title = 'Quitar'; q.onclick = function () { ADJ.splice(ADJ.indexOf(x), 1); pintarAdjuntos(); };
    c.appendChild(q); w.appendChild(c);
  });
  w.style.display = ADJ.length ? '' : 'none';
}
function adjuntar(files) {
  var a = activo(); if (!a) return;
  [].slice.call(files || []).forEach(function (f) {
    var x = { nombre: f.name }; ADJ.push(x); pintarAdjuntos();
    if (f.size > 20 * 1024 * 1024) { x.mal = 'Pasa de 20 MB'; return pintarAdjuntos(); }
    var rd = new FileReader();
    rd.onload = function () {
      post('/api/adjunto', { agente: a.id, nombre: f.name, datos: String(rd.result).split(',')[1] || '' }).then(function (r) { x.ruta = r.ruta; pintarAdjuntos(); pintarSend(); },
        function (e) { x.mal = e.message; pintarAdjuntos(); });
    };
    rd.readAsDataURL(f);
  });
}
function conAdjuntos(t) {
  var listos = ADJ.filter(function (x) { return x.ruta; });
  if (!listos.length) return t;
  return (t ? t + ' ' : '') + '(adjunté: ' + listos.map(function (x) { return x.ruta; }).join(', ') + ')';
}
function adjuntosPendientes() { return ADJ.some(function (x) { return !x.ruta && !x.mal; }); }
function limpiarAdjuntos() { ADJ = []; pintarAdjuntos(); }

/* dictado: el reconocimiento de voz del navegador escribe en vivo en la caja */
function prepararVoz() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition, b = $('#voz');
  if (!SR) { b.remove(); return; }
  b.appendChild(icono('mic')); var ondas = el('i', 'ondas'); ondas.appendChild(el('i')); ondas.appendChild(el('i')); ondas.appendChild(el('i')); b.appendChild(ondas);
  var rec = null, base = '', ta = $('#ta');
  b.onclick = function () {
    if (rec) { rec.stop(); return; }
    try { rec = new SR(); } catch (e) { return nota('No pude usar el micrófono: ' + e.message, true); }
    rec.lang = 'es-MX'; rec.interimResults = true; rec.continuous = true;
    base = ta.value ? ta.value.replace(/\s*$/, ' ') : '';
    rec.onresult = function (e) {
      var fin = '', tmp = '';
      for (var i = 0; i < e.results.length; i++) { if (e.results[i].isFinal) fin += e.results[i][0].transcript; else tmp += e.results[i][0].transcript; }
      ta.value = base + fin + tmp; ta.dispatchEvent(new Event('input'));
    };
    rec.onerror = function (ev) { if (ev.error !== 'aborted' && ev.error !== 'no-speech') nota(ev.error === 'not-allowed' ? 'Dale permiso al navegador para usar el micrófono.' : 'Dictado: ' + ev.error, true); };
    rec.onend = function () { rec = null; b.classList.remove('on'); ta.focus(); };
    rec.start(); b.classList.add('on'); ta.focus();
  };
}
function prepararSoltar() {
  var z = $('.mid');
  z.addEventListener('dragover', function (e) { if (e.dataTransfer && [].indexOf.call(e.dataTransfer.types || [], 'Files') >= 0) { e.preventDefault(); z.classList.add('soltar'); } });
  z.addEventListener('dragleave', function (e) { if (!z.contains(e.relatedTarget)) z.classList.remove('soltar'); });
  z.addEventListener('drop', function (e) { if (!e.dataTransfer || !e.dataTransfer.files.length) return; e.preventDefault(); z.classList.remove('soltar'); adjuntar(e.dataTransfer.files); });
}

/* ================= skills v11 · cuando el agente te pregunta algo, por la caja de escribir (Q-2) =================
   La franja crece dentro de la caja con la pregunta, sus respuestas de un toque y «Responder después»; toda la caja se
   enmarca en el color del agente mientras espera y pide «Escribe tu respuesta…». «Responder después» deja solo la píldora
   («{Agente} espera tu respuesta · Responder») y la caja vuelve a ser normal; la skill sigue en pausa. Al contestar, la
   franja se repliega mientras tu respuesta vuela al chat. La pregunta llega del evento de la capa de control
   (MCP núcleo · preguntar: foto.pregunta) y la respuesta va por /api/v2/responder. */
var QZ = { modo: '', el: null, ag: '', id: '' };
/* Enter o el botón de enviar: con la franja abierta contestan (con la caja vacía, solo ponen el foco); si no, mandan */
function enviarCaja() {
  var a = activo(), ta = $('#ta');
  if (a && modoCaja(a) === 'abierta') { var v = ta.value.trim(); if (!v) { ta.focus(); return; } return responderPregunta(a, preguntaDe(a), v, 'texto'); }
  mandar(ta.value);
}
var CURVA11 = 'cubic-bezier(.22,1,.36,1)', CIERRA11 = 'cubic-bezier(.4,0,.2,1)';
function opcionesDe(q) { return q.tipo === 'confirmar' ? ['Sí', 'No'] : (q.opciones || []).slice(0, 6); }
/* normal · abierta · pildora: la pregunta pendiente vive en el chat de SU agente; en el de otro, la caja es normal */
function modoCaja(a) { var q = preguntaDe(a); return !q ? (pendienteDe(a) ? 'pendiente' : '') : L(a).despues === q.id ? 'pildora' : 'abierta'; }
/* skills-cierre · decisión del 22-nov: si le escribiste otra cosa a media pregunta, la skill se pausa en silencio y aquí
   queda una pastilla «Quedó pendiente: ¿…? · Seguir / Cerrar». Solo vuelve a preguntar si pulsas Seguir. */
function pendienteDe(a) {
  var e = a && (S.ejec[a.id] || [])[0], p = (e && e.pausa) || {};
  if (!e || e.estado !== 'pausada' || p.motivo !== 'otro_mensaje' || !p.pendiente || p.cerrada) return null;
  if ((L(a).cerradas || {})[e.id] || detenida(a, e)) return null;
  var t = Date.parse(e.actualizado || e.creado || '') || 0;
  return !t || Date.now() - t < 6 * 3600 * 1000 ? e : null;
}
function signoQ() { return svgTexto('<svg class="qb11" width="10" height="16" viewBox="-9.5 -17.5 19 35" aria-hidden="true"><path d="M-6.5 -7C-6.5 -14.5 6.5 -14.5 6.5 -7 6.5 -2 0 -1.5 0 3.5" stroke="currentColor" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="0" cy="11.5" r="3.6" fill="currentColor"/></svg>'); }
function contenidoQZ(a, q, modo) {
  var w = el('div');
  if (modo === 'pendiente') {
    var e = pendienteDe(a), pe = el('div', 'qzpe11');
    pe.appendChild(el('span', null, 'Quedó pendiente:')); pe.appendChild(el('b', null, (e.pausa || {}).pendiente));
    var sg = el('button', 'bt5 ac', 'Seguir'); sg.onclick = function (ev) { ev.stopPropagation(); seguirSkill(a, e); }; pe.appendChild(sg);
    var ce = el('button', 'bt5', 'Cerrar'); ce.onclick = function (ev) { ev.stopPropagation(); cerrarPausada(a, e); pintarComposer(true); }; pe.appendChild(ce);
    w.appendChild(pe);
    return w;
  }
  if (modo === 'abierta') {
    var c = el('div', 'qzc11'), h = el('div', 'qzh11'), m = el('span', 'qzm11');
    m.appendChild(monitoDe('qz-' + q.id, a, 24)); m.appendChild(signoQ()); h.appendChild(m);
    var t = el('div', 'qzt11'); t.appendChild(el('span', null, a.n + ' te pregunta:')); t.appendChild(el('b', null, q.pregunta)); h.appendChild(t);
    var d = el('button', 'qzd11', 'Responder después'); d.title = 'La skill sigue en pausa hasta que contestes';
    d.onclick = function (e) { e.stopPropagation(); L(a).despues = q.id; pintarComposer(true); pintarActiva(); };
    h.appendChild(d); c.appendChild(h);
    var ops = opcionesDe(q);
    if (ops.length) {
      var o = el('div', 'qzo11');
      ops.forEach(function (x) {
        var b = el('button', 'op10', x);
        /* la pestaña se toma al tocar (no 150 ms después, al terminar su animación): la respuesta es de ahí */
        b.onclick = function (e) { e.stopPropagation(); if (b._va) return; b._va = true; b.classList.add('elegida'); var tab = tabDe(a); setTimeout(function () { responderPregunta(a, q, x, b, tab); }, 150); };
        o.appendChild(b);
      });
      c.appendChild(o);
    }
    w.appendChild(c);
  } else {
    var p = el('button', 'qzp11'); p.appendChild(el('i', 'pulso10')); p.appendChild(el('span', null, a.n + ' espera tu respuesta')); p.appendChild(el('b', null, 'Responder'));
    p.onclick = function (e) { e.stopPropagation(); verPregunta(a); };
    w.appendChild(p);
  }
  return w;
}
/* la caja: normal, con la franja abierta o con la píldora; crece hacia arriba y se repliega sin rebote */
function pintarComposer(anim) {
  var B = $('.box'), a = activo(); if (!B) return;
  var q = a && preguntaDe(a), modo = a ? modoCaja(a) : '', ta = $('#ta');
  B.classList.toggle('pregunta11', modo === 'abierta' || modo === 'pildora'); B.classList.toggle('responde11', modo === 'abierta'); B.classList.toggle('espera11', modo === 'pildora');
  B.classList.toggle('pendiente11', modo === 'pendiente');
  if (!ta.disabled) ta.placeholder = modo === 'abierta' ? 'Escribe tu respuesta…' : placeholderDe(a);
  var clave = modo ? modo + '|' + (q ? q.id : pendienteDe(a).id) : '';
  if (clave === QZ.modo && QZ.ag === (a && a.id) && (!modo || (QZ.el && QZ.el.isConnected))) { pintarSend(); return; }
  var viejo = QZ.el && QZ.el.isConnected ? QZ.el : null;
  QZ.modo = clave; QZ.ag = a && a.id; anim = anim && MOV;
  pintarSend();
  if (!modo) { QZ.el = null; if (viejo) cerrarQZ(viejo, anim); return; }
  var w = viejo || el('div', 'qz11'); if (!viejo) B.insertBefore(w, B.firstChild);
  w.getAnimations().forEach(function (x) { x.cancel(); });
  var h0 = viejo ? w.offsetHeight : 0, ant = viejo && anim ? w.firstChild : null;
  if (ant) { ant.style.cssText += ';position:absolute;left:0;right:0;top:0;pointer-events:none'; ant.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, easing: 'ease-out', fill: 'forwards' }).onfinish = function () { ant.remove(); }; }
  else w.textContent = '';
  var cont = contenidoQZ(a, q, modo); w.appendChild(cont); QZ.el = w;
  if (!anim) return;
  var h1 = w.offsetHeight;
  w.animate([{ height: h0 + 'px' }, { height: h1 + 'px' }], { duration: 420, easing: CURVA11 });
  cont.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 300, delay: ant ? 110 : 70, easing: CURVA11, fill: 'backwards' });
  cont.querySelectorAll('.op10').forEach(function (b, i) { b.animate([{ opacity: 0, transform: 'translateY(5px) scale(.96)' }, { opacity: 1, transform: 'none' }], { duration: 260, delay: 170 + i * 50, easing: CURVA11, fill: 'backwards' }); });
  pegarAbajo(480);
}
function cerrarQZ(w, anim) {
  if (!anim) { w.remove(); return; }
  w.getAnimations().forEach(function (x) { x.cancel(); });
  var h = w.offsetHeight; w.style.pointerEvents = 'none';
  w.animate([{ height: h + 'px', opacity: 1 }, { height: h * .6 + 'px', opacity: 0, offset: .45 }, { height: '0px', opacity: 0 }], { duration: 380, easing: CIERRA11, fill: 'forwards' }).onfinish = function () { w.remove(); };
}
function destelloBox(B) {
  if (!MOV || !B) return;
  B.animate([{ borderColor: '#2c2c32' }, { borderColor: getComputedStyle(B).getPropertyValue('--ac').trim() || '#ededf0' }, { borderColor: '#2c2c32' }], { duration: 1000, easing: 'ease-in-out' });
}
/* «Esperando tu respuesta abajo» y la píldora: abren la franja, ponen el cursor en la caja y su borde destella */
function verPregunta(a) {
  if (!preguntaDe(a)) return;
  if (S.act !== a.id) elegirAgente(a.id);
  if (L(a).despues) { L(a).despues = null; pintarComposer(true); pintarActiva(); }
  setTimeout(function () { $('#ta').focus({ preventScroll: true }); destelloBox($('.box')); }, 60);
}
/* cubic-bezier(.4,0,.2,1): sale decidido y se detiene limpio */
function bezier(x1, y1, x2, y2) {
  function cx(t, a, b) { return 3 * a * t * (1 - t) * (1 - t) + 3 * b * t * t * (1 - t) + t * t * t; }
  return function (x) { if (x <= 0) return 0; if (x >= 1) return 1; var lo = 0, hi = 1, t = x; for (var i = 0; i < 22; i++) { t = (lo + hi) / 2; if (cx(t, x1, x2) < x) lo = t; else hi = t; } return cx(t, y1, y2); };
}
var EASE11 = bezier(.4, 0, .2, 1);
function rgbDe(c) { var m = ((c || '').match(/[\d.]+/g) || [0, 0, 0, 0]).map(Number); if (/^color\(srgb/.test(c)) m = m.map(function (v, i) { return i < 3 ? v * 255 : v; }); return [m[0] || 0, m[1] || 0, m[2] || 0, m.length > 3 ? m[3] : 1]; }
function mezcla(a, b, p) { return 'rgba(' + [0, 1, 2].map(function (i) { return Math.round(a[i] + (b[i] - a[i]) * p); }).join(',') + ',' + (a[3] + (b[3] - a[3]) * p).toFixed(3) + ')'; }
/* el rect del texto escrito dentro de la caja (de ahí sale volando) */
function rectoTexto(ta, t) {
  var r = ta.getBoundingClientRect(), cs = getComputedStyle(ta), m = el('span');
  m.style.cssText = 'position:fixed;left:-9999px;visibility:hidden;white-space:pre;font:' + cs.font; m.textContent = t; document.body.appendChild(m);
  var w = Math.min(r.width - 8, m.offsetWidth + 2); m.remove();
  return { left: r.left + parseFloat(cs.paddingLeft), top: r.top + parseFloat(cs.paddingTop), width: w, height: parseFloat(cs.lineHeight) || 20 };
}
/* tu respuesta vuela de la caja (o de la respuesta rápida) al chat y se vuelve tu burbuja: el destino se lee en cada
   cuadro (el chat cambia de alto mientras la franja se repliega) */
function volarA(b, r0, t, src) {
  if (!MOV || !r0 || !b) return;
  var chip = !!(src && src.nodeType === 1), cs0 = getComputedStyle(chip ? src : $('#ta')), csb = getComputedStyle(b), spn = b.querySelector('span'), css = getComputedStyle(spn);
  var bg0 = chip ? rgbDe(cs0.backgroundColor) : [30, 30, 34, 0], bg1 = rgbDe(csb.backgroundColor), co0 = rgbDe(cs0.color), co1 = rgbDe(css.color);
  var fs0 = parseFloat(cs0.fontSize), fs1 = parseFloat(css.fontSize), pt1 = parseFloat(csb.paddingTop), pl1 = parseFloat(csb.paddingLeft), pl0 = chip ? parseFloat(cs0.paddingLeft) : 0;
  var rad0 = chip ? r0.height / 2 : 6;
  b.style.visibility = 'hidden'; if (chip) src.style.visibility = 'hidden';
  var c = el('div', 'vuela11'), cl = el('small', null, 'Tu respuesta'); c.appendChild(cl); c.appendChild(el('span', null, t)); c.style.lineHeight = css.lineHeight;
  if (spn.getClientRects().length <= 1) c.style.whiteSpace = 'nowrap';
  document.body.appendChild(c);
  var t0 = performance.now(), dur = 380;
  pegarAbajo(dur + 200);
  function paso(ahora) {
    var k = Math.min(1, (ahora - t0) / dur), p = EASE11(k), r1 = b.getBoundingClientRect(), q = Math.min(1, p * 1.5);
    var R = rad0 + (20 - rad0) * p, Rt = rad0 + (8 - rad0) * p;
    c.style.left = (r0.left + (r1.left - r0.left) * p) + 'px'; c.style.top = (r0.top + (r1.top - r0.top) * p) + 'px';
    c.style.width = (r0.width + (r1.width - r0.width) * p) + 'px'; c.style.height = (r0.height + (r1.height - r0.height) * p) + 'px';
    c.style.borderRadius = R + 'px'; c.style.borderTopRightRadius = Rt + 'px';
    c.style.padding = (pt1 * p) + 'px ' + (pl0 + (pl1 - pl0) * p) + 'px';
    c.style.background = mezcla(bg0, bg1, q); c.style.color = mezcla(co0, co1, q);
    c.style.fontSize = (fs0 + (fs1 - fs0) * p) + 'px'; c.style.fontWeight = p < .5 ? '600' : '400';
    cl.style.opacity = Math.max(0, (p - .55) / .45); cl.style.maxHeight = (p * 18) + 'px'; cl.style.marginBottom = (p * 2) + 'px';
    if (k < 1) requestAnimationFrame(paso); else { b.style.visibility = ''; c.remove(); }
  }
  requestAnimationFrame(paso);
}
/* contestar: todo a la vez (se repliega la franja, vuela tu respuesta, el proceso suma «Tu respuesta» y el monito hace
   «idea»); la respuesta va por la capa de control al mismo motor. `tab`: la pestaña donde la contestaste (sin ella, la
   que ves); la respuesta y su rastro van a esa, como mandar */
function responderPregunta(a, q, t, src, tab) {
  t = String(t || '').trim(); if (!t) return;
  if (tab === undefined) tab = tabDe(a);
  var ta = $('#ta'), r0 = null, l = L(a, tab);
  if (src && src.nodeType === 1) r0 = src.getBoundingClientRect(); else if (src === 'texto') r0 = rectoTexto(ta, t);
  l.resp = { id: q.id, q: q.pregunta, t: t, ts: Date.now() }; l.despues = null;
  var run = corrida(a); if (run) { var F = feedDe(a, run); F.xs.unshift({ txt: 'Tu respuesta: ' + t, t: Date.now(), nuevo: true }); }
  if (src === 'texto') limpiarCaja();
  pintarEstadoVivo();
  var b = document.querySelector('#col .resp11.local');
  if (b) { var f = $('#feed'); f.style.scrollBehavior = 'auto'; f.scrollTop = f.scrollHeight; f.style.scrollBehavior = ''; volarA(b, r0, t, src); }
  pintarComposer(true); pintarActiva();
  post('/api/v2/responder', { agente: a.id, id: q.id, texto: t, tab: tab }).then(function () { acelerar(20); }, function (e) {
    nota(e.message, true); l.resp = null; pintarEstadoVivo(); pintarComposer(true); pintarActiva();
  });
}
