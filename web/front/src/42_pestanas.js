/* ================= H4-a «pestañas en el borde»: varias conversaciones por agente =================
   ⌂ Conversación (la de siempre) va primero y no se cierra; después, sus sesiones abiertas como pestañas: las mismas
   que en el hub (las guarda Workspace, no esta vista) y las mismas que abres en su programa oficial. «+» abre una
   conversación nueva (con el motor que elijas) o una de sus sesiones; × la cierra (no se borra nada) con «Deshacer».
   Las que no caben van en «+N ▾». Teclas: Alt+1…9 cambia, Alt+T abre «+», Alt+W cierra la que ves. */
var TAB_EST = { trabajando: 'trab', esperandote: 'espera', termino: 'listo', error: 'mal' };
var TAB_DESHACER_MS = 8000;
function restaurarTabs() { var g = pagGet('tabs'); if (g && typeof g === 'object' && !Array.isArray(g)) S.tab = Object.assign({}, g); }
function guardarTabs() { pagSet('tabs', S.tab); }
function nombreTab(x) { return x.slug === NAV ? 'Conversación' : (x.nombre || x.slug); }
function fotoDeTab(a, slug) { var f = S.vivoCrudo[a.id] || {}; return slug === NAV ? f : (f.tab_fotos || {})[slug] || {}; }
function estadoTab(a, x) { return fotoDeTab(a, x.slug).estado || x.estado || ''; }
/* cambia la conversación que ves de `a` (lo escrito se queda con la suya); `recien`: se acaba de abrir y su foto
   todavía no llega */
function elegirTab(a, slug, recien) {
  if (!a) return;
  slug = slug || NAV;
  if (tabDe(a) === slug && !recien) return;
  var ta = $('#ta');
  if (S.act === a.id) { L(a).borrador = ta.value; L(a).adj = ADJ; }
  S.tab[a.id] = slug;
  if (recien && slug !== NAV) S.tabPend[a.id] = { slug: slug, t: Date.now() };
  guardarTabs();
  var f = S.vivoCrudo[a.id]; if (f) ponerFoto(a.id, f);
  S.conv[a.id] = S.convs[a.id + '|' + slugChat(a)] || null;
  if (S.act === a.id) { ta.value = L(a).borrador || ''; ADJ = L(a).adj || []; pintarAdjuntos(); }
  pintar(true); acelerar(); sondeoChat();
}
function pintarTabs() {
  var T = $('#tabs'), a = activo();
  if (!T) return;
  if (!a) { T.textContent = ''; T._f = ''; return; }
  var tira = tiraDe(a), act = tabDe(a), pe = S.tabPend[a.id];
  var f0 = firma(JSON.stringify([a.id, a.c, act, T.clientWidth, tira.map(function (x) { return [x.slug, nombreTab(x), x.motor, estadoTab(a, x), !!x.terminal, !!x.solo_mirar]; })]));
  if (T._f === f0) return;
  T._f = f0; T.textContent = '';
  T.style.setProperty('--ac', a.c);
  var botones = tira.map(function (x, i) { var b = botonTab(a, x, i, x.slug === act); if (pe && pe.slug === x.slug && Date.now() - pe.t < 1500) b.classList.add('nuevo'); T.appendChild(b); return b; });
  var mas = el('button', 'tab abre'); mas.appendChild(icono('plus')); mas.title = 'Otra conversación: nueva o una de sus sesiones (Alt+T)';
  mas.onclick = function (e) { e.stopPropagation(); menuTabs(mas, a); };
  T.appendChild(mas);
  /* las que no caben van en «+N ▾» (nunca ⌂ ni la que ves), de la última a la primera */
  var fuera = [], sobra = null;
  for (var i = botones.length - 1; i > 0 && T.scrollWidth > T.clientWidth + 1; i--) {
    if (tira[i].slug === act) continue;
    botones[i].remove(); fuera.unshift(tira[i]);
    if (!sobra) { sobra = el('button', 'tab sobra'); T.insertBefore(sobra, mas); }
    sobra.textContent = '+' + fuera.length + ' ▾';
  }
  if (sobra) {
    sobra.title = 'Sus otras pestañas';
    sobra.onclick = function (e) { e.stopPropagation(); pop(sobra, fuera.map(function (x) { return { t: nombreTab(x), sub: motorN(x.motor), run: function () { elegirTab(a, x.slug); } }; }), 'Sus otras pestañas'); };
  }
}
function botonTab(a, x, i, on) {
  var b = el('button', 'tab' + (on ? ' on' : '') + (x.slug === NAV ? ' casa' : ''));
  b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', on ? 'true' : 'false');
  b.appendChild(el('i', 'td ' + (TAB_EST[estadoTab(a, x)] || '')));
  b.appendChild(el('span', 'tn', (x.slug === NAV ? '⌂ ' : '') + nombreTab(x)));
  if (x.terminal) b.appendChild(el('small', 'tt', '↗'));
  b.title = nombreTab(x) + (x.slug === NAV ? ' · la de siempre' : ' · ' + motorN(x.motor) + (x.solo_mirar ? ' · aquí solo se mira' : '')) + (i < 9 ? ' · Alt+' + (i + 1) : '');
  b.onclick = function (e) { e.stopPropagation(); elegirTab(a, x.slug); };
  if (x.slug !== NAV) {
    var c = el('span', 'tx', '×'); c.title = 'Cerrar la pestaña (no se borra: sigue en sus sesiones) · Alt+W';
    c.onclick = function (e) { e.stopPropagation(); cerrarTab(a, x.slug); };
    b.appendChild(c);
  }
  return b;
}
/* «+»: una conversación nueva (con el motor que elijas) o una de sus sesiones: la misma lista que en el hub (S-1) */
function menuTabs(anc, a) {
  var usable = function (m) { return m.listo && m.sesion !== false && m.estado !== 'sin_sesion'; };
  var base = a.motor, filas = [{ t: 'Conversación nueva', sub: 'con ' + motorN(base), run: function () { abrirTab(a, { nueva: true, motor: base }); } }];
  S.motores.filter(function (m) { return usable(m) && m.id !== base; }).slice(0, 5).forEach(function (m) {
    filas.push({ t: 'Nueva con ' + m.nombre, run: function () { abrirTab(a, { nueva: true, motor: m.id }); } });
  });
  filas.push('-');
  var titulo = 'Abrir en una pestaña · Alt+T';
  /* la respuesta es de ESTE menú: si ya lo cerraste (o abriste otro), llega tarde y se descarta */
  var menu = pop(anc, filas.concat([{ t: 'Buscando sus sesiones…', off: true }]), titulo);
  var sigue = function () { return !!(menu && menu.isConnected); };
  api('/api/v2/sesiones?agente=' + encodeURIComponent(a.id)).then(function (d) {
    if (!sigue()) return;
    var abiertas = {}; tiraDe(a).forEach(function (x) { abiertas[x.slug] = 1; });
    var ses = (d.sesiones || []).map(function (s) {
      var ya = !!abiertas[s.slug], c = Date.parse(s.cuando || '');
      return { t: s.nombre || s.slug, sub: motorN(s.motor) + ' · ' + (ya ? 'ya abierta' : (c ? cuando(c) : '')),
        run: function () { if (ya) elegirTab(a, s.slug); else abrirTab(a, { slug: s.slug }); } };
    });
    pop(anc, filas.concat(ses.length ? [{ t: 'Sus sesiones · las mismas que abres en su programa oficial', off: true }].concat(ses)
      : [{ t: 'Todavía no tiene otras sesiones', off: true }]), titulo);
  }, function () { if (sigue()) pop(anc, filas.concat([{ t: 'No pude leer sus sesiones', off: true }]), titulo); });
}
function abrirTab(a, q) {
  post('/api/v2/tab/abrir', Object.assign({ agente: a.id }, q)).then(function (r) {
    if (r.tab) elegirTab(a, r.tab.slug, true);
    if (r.cerrada) notaDeshacer(a, 'Cerré «' + r.cerrada.nombre + '», la que llevabas más tiempo sin ver. Sigue en sus sesiones.');
  }, function (e) { nota(e.message, true); });
}
function cerrarTab(a, slug) {
  var tira = tiraDe(a), i = tira.map(function (x) { return x.slug; }).indexOf(slug);
  if (tabDe(a) === slug) elegirTab(a, ((tira[i - 1] || tira[0]) || {}).slug || NAV);
  post('/api/v2/tab/cerrar', { agente: a.id, tab: slug }).then(function (r) {
    if (r.cerrada) notaDeshacer(a, 'Cerré «' + r.cerrada.nombre + '». No se borró: sigue en sus sesiones.');
    acelerar();
  }, function (e) { nota(e.message, true); });
}
/* el aviso de una línea con «Deshacer» (la vuelve a abrir en su lugar) */
function notaDeshacer(a, t) {
  document.querySelectorAll('.nota.deshacer').forEach(function (n) { n.remove(); });
  var n = el('div', 'nota deshacer'); n.appendChild(el('span', null, t));
  var b = el('button', null, 'Deshacer');
  b.onclick = function (e) {
    e.stopPropagation(); n.remove();
    post('/api/v2/tab/deshacer', { agente: a.id }).then(function (r) { if (r.tab) elegirTab(a, r.tab.slug, true); }, function (x) { nota(x.message, true); });
  };
  n.appendChild(b); document.body.appendChild(n);
  setTimeout(function () { n.remove(); }, TAB_DESHACER_MS);
}
function teclasTabs(e) {
  if (!e.altKey || e.ctrlKey || e.metaKey) return;
  var a = activo(), c = e.code || ''; if (!a) return;
  if (/^Digit[1-9]$/.test(c)) { var x = tiraDe(a)[+c.slice(5) - 1]; if (x) { e.preventDefault(); elegirTab(a, x.slug); } return; }
  if (c === 'KeyT') { e.preventDefault(); e.stopPropagation(); menuTabs($('#tabs .abre') || $('#tabs'), a); return; }
  if (c === 'KeyW' && tabDe(a) !== NAV) { e.preventDefault(); cerrarTab(a, tabDe(a)); }
}
addEventListener('resize', function () { var T = $('#tabs'); if (T) { T._f = ''; pintarTabs(); } });
