/* ================= ayudantes de interfaz (sin datos) ================= */
function $(s, r) { return (r || document).querySelector(s); }
function el(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
var ICO = {
  plus: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M10 4v12M4 10h12"/></svg>',
  chev: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 4.5l3 3 3-3"/></svg>',
  der: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M4.5 2.5L8 6l-3.5 3.5"/></svg>',
  up: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 13V3.5M4 7.5l4-4 4 4"/></svg>',
  stop: '<svg width="14" height="14" viewBox="0 0 14 14"><rect x="3" y="3" width="8" height="8" rx="1.5" fill="currentColor"/></svg>',
  mic: '<svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="6.5" y="2.5" width="5" height="8.5" rx="2.5"/><path d="M4 8.5a5 5 0 0 0 10 0M9 13.5v2.5"/></svg>',
  x: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
  lapiz: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M2.5 11.5l.6-2.6 6.4-6.4 2 2-6.4 6.4z"/></svg>',
  skill: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M3 4.5h10M3 8h6M3 11.5h8"/><circle cx="12.5" cy="8" r="1.4" fill="currentColor" stroke="none"/></svg>',
  doc: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/></svg>',
  term: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="3.5" width="15" height="13" rx="2.5"/><path d="M6 8l2.5 2L6 12M10.5 12.5H14"/></svg>'
};
/* los íconos se arman con DOMParser (nada de asignar HTML como texto: la página no usa esa API) */
var _PARSER = new DOMParser();
/* sin xmlns, el SVG parseado queda fuera del espacio de nombres SVG y no se dibuja */
function icono(k) { var d = _PARSER.parseFromString(ICO[k].replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" '), 'image/svg+xml'); return document.importNode(d.documentElement, true); }
function svg(k, cls) { var s = el('span', cls); s.style.display = 'inline-flex'; s.appendChild(icono(k)); return s; }
function claroHex(c) { try { return claro(c); } catch (_) { return false; } }
function cerrarCapas() { document.querySelectorAll('.pop').forEach(function (p) { p.remove(); }); }
function pop(ancla, filas, titulo, arriba) {
  cerrarCapas();
  var p = el('div', 'pop'); if (titulo) p.appendChild(el('div', 'h', titulo));
  filas.forEach(function (f) {
    if (f === '-') return p.appendChild(el('hr'));
    var b = el('button', f.rojo ? 'rojo' : ''); if (f.marca) b.appendChild(f.marca); b.appendChild(el('span', null, f.t));
    if (f.sub) b.appendChild(el('small', null, f.sub)); if (f.ok) b.appendChild(el('span', 'ok', '✓'));
    if (f.off) { b.disabled = true; b.style.opacity = '.45'; } else if (f.tenue) b.style.opacity = '.6';
    b.onclick = function (e) { e.stopPropagation(); cerrarCapas(); if (f.run) f.run(); }; p.appendChild(b);
  });
  document.body.appendChild(p);
  var r = ancla.getBoundingClientRect(), h = p.offsetHeight, w = p.offsetWidth;
  p.style.top = Math.max(8, arriba || r.bottom + h + 8 > innerHeight ? r.top - h - 8 : r.bottom + 8) + 'px';
  p.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left)) + 'px';
  return p;
}
document.addEventListener('click', cerrarCapas);
function nota(t, mal, ms) { var n = el('div', 'nota' + (mal ? ' mal' : ''), t); document.body.appendChild(n); setTimeout(function () { n.remove(); }, ms || (mal ? 4200 : 2400)); }
var TIP = null;
function quitarTip() { if (TIP) { TIP.remove(); TIP = null; } }
function tip(e, t, sub) { quitarTip(); TIP = el('div', 'tip', t); if (sub) TIP.appendChild(el('small', null, sub)); document.body.appendChild(TIP); var r = e.getBoundingClientRect(); TIP.style.left = (r.right + 10) + 'px'; TIP.style.top = (r.top + r.height / 2 - TIP.offsetHeight / 2) + 'px'; TIP._anc = e; e.onmouseleave = quitarTip; }
addEventListener('mousemove', function () { if (TIP && (!TIP._anc.isConnected || !TIP._anc.matches(':hover'))) quitarTip(); });
function anillo(px, pct, txt, col) {
  var w = el('div', 'anillo'), r = px / 2 - 5, L = 2 * Math.PI * r, sv = NS('svg', { width: px, height: px, viewBox: '0 0 ' + px + ' ' + px });
  w.style.width = px + 'px'; w.style.height = px + 'px';
  sv.appendChild(NS('circle', { cx: px / 2, cy: px / 2, r: r, fill: 'none', stroke: '#2c2c33', 'stroke-width': 6 }));
  if (pct > 0) sv.appendChild(NS('circle', { cx: px / 2, cy: px / 2, r: r, fill: 'none', stroke: col, 'stroke-width': 6, 'stroke-linecap': 'round', 'stroke-dasharray': (L * Math.min(1, pct)) + ' ' + L, transform: 'rotate(-90 ' + px / 2 + ' ' + px / 2 + ')' }));
  w.appendChild(sv); w.appendChild(el('b', null, txt)); return w;
}
function chevDer() { var s = el('span', 'ch'); s.appendChild(icono('der')); return s; }
function cuando(ts) {
  if (!ts) return '';
  var d = (Date.now() - (ts > 1e12 ? ts : ts * 1000)) / 1000;
  if (d < 60) return 'ahora'; if (d < 3600) return 'hace ' + Math.round(d / 60) + ' min'; if (d < 86400) return 'hace ' + Math.round(d / 3600) + ' h';
  if (d < 172800) return 'ayer'; return 'hace ' + Math.round(d / 86400) + ' días';
}

/* ---------- render incremental ----------
   Cada pieza trae una clave (quién es) y una firma (cómo se ve). Si la firma no cambió, el nodo se reusa tal cual:
   nada se vuelve a dibujar ni a animar (eso era el parpadeo). Solo lo que aparece por primera vez entra animado. */
function firma(s) { s = String(s); var h = 5381; for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return s.length + ':' + h; }
function reconciliar(C, piezas, grupo) {
  var inicial = !C._mapa || C._grupo !== grupo, viejos = inicial ? {} : C._mapa, nuevos = {}, i = 0;
  piezas.forEach(function (p) {
    var v = viejos[p.k], n;
    if (v && v.f === p.f) n = v.n;
    else { n = p.hacer(); if (!inicial && !v && !p.quieto) n.classList.add('nuevo'); }
    nuevos[p.k] = { f: p.f, n: n };
    if (C.children[i] !== n) C.insertBefore(n, C.children[i] || null);
    i++;
  });
  while (C.children.length > i) C.removeChild(C.lastChild);
  C._mapa = nuevos; C._grupo = grupo;
}
