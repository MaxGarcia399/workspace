/* Monitos de Workspace: el personaje de cada agente.
   Silueta lisa (6 formas) que se deforma por cuadro (150 puntos + Catmull-Rom), ojos de pastilla que siguen el cursor,
   signos planos de su color y gestos según su estado (libre, trabaja, pregunta, termino, error, duerme).
   Los monitos chicos (<60 px) van sin signos, con encuadre justo y más movimiento. */
var COLS = ['#ff4fa3', '#3fbf7f', '#3b82f6', '#e7a43a', '#8b5cf6', '#ffffff'];
var FORMAS6 = ['bolita', 'pico', 'cuadrito', 'gatito', 'fantasma', 'nube'];
var PATH = {
  bolita: 'M50 12C74 12 90 30 90 54S74 92 50 92 10 78 10 54 26 12 50 12Z',
  pico: 'M50 10C58 10 64 20 72 34 82 52 92 66 92 78 92 90 82 94 50 94S8 90 8 78C8 66 18 52 28 34 36 20 42 10 50 10Z',
  cuadrito: 'M28 14H72C84 14 90 20 90 32V74C90 86 84 92 72 92H28C16 92 10 86 10 74V32C10 20 16 14 28 14Z',
  gatito: 'M18 30 16 8 38 22C42 21 46 20 50 20S58 21 62 22L84 8 82 30C88 38 91 46 91 56 91 78 74 92 50 92S9 78 9 56C9 46 12 38 18 30Z',
  fantasma: 'M50 10C72 10 88 26 88 50V90L78 82 68 90 58 82 50 90 42 82 32 90 22 82 12 90V50C12 26 28 10 50 10Z',
  nube: 'M30 92C16 92 8 84 8 72 8 60 16 52 26 52 26 36 38 24 54 24 68 24 78 34 80 46 90 48 94 58 94 66 94 82 84 92 70 92Z'
};
function hex2(c) { var n = parseInt(c.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
function claro(c) { var r = hex2(c); return (r[0] * 299 + r[1] * 587 + r[2] * 114) / 1000 > 150; }
function NS(t, a) { var e = document.createElementNS('http://www.w3.org/2000/svg', t); for (var k in a || {}) e.setAttribute(k, a[k]); return e; }
/* ===== la silueta como puntos, para poder deformarla ===== */
var HOJA = NS('svg', { width: 0, height: 0, style: 'position:absolute' }); document.body.appendChild(HOJA);
var PUNTOS = {};
function puntos(f) {
  if (PUNTOS[f]) return PUNTOS[f];
  var p = NS('path', { d: PATH[f] }); HOJA.appendChild(p);
  var L = p.getTotalLength(), n = 150, pts = [], y0 = 1e9, y1 = -1e9;
  for (var i = 0; i < n; i++) { var q = p.getPointAtLength(L * i / n); pts.push([q.x, q.y]); y0 = Math.min(y0, q.y); y1 = Math.max(y1, q.y); }
  p.remove();
  return (PUNTOS[f] = { pts: pts, top: y0, base: y1 });
}
/* curva suave que pasa por todos los puntos (Catmull-Rom → Bézier) */
function curva(P) {
  var n = P.length, d = 'M' + P[0][0].toFixed(2) + ' ' + P[0][1].toFixed(2);
  for (var i = 0; i < n; i++) {
    var p0 = P[(i - 1 + n) % n], p1 = P[i], p2 = P[(i + 1) % n], p3 = P[(i + 2) % n];
    d += 'C' + (p1[0] + (p2[0] - p0[0]) / 6).toFixed(2) + ' ' + (p1[1] + (p2[1] - p0[1]) / 6).toFixed(2) + ' ' + (p2[0] - (p3[0] - p1[0]) / 6).toFixed(2) + ' ' + (p2[1] - (p3[1] - p1[1]) / 6).toFixed(2) + ' ' + p2[0].toFixed(2) + ' ' + p2[1].toFixed(2);
  }
  return d + 'Z';
}
/* suavizado sin rebote (para casi todo) y un resorte suave (solo para la gelatina) */
function hacia(v, t, k, dt) { return v + (t - v) * (1 - Math.exp(-k * dt)); }
function Gel(k, d) { this.v = 0; this.vel = 0; this.k = k; this.d = d; }
Gel.prototype.paso = function (dt) { this.vel += (-this.k * this.v - this.d * this.vel) * dt; this.v += this.vel * dt; };
/* ruido suave (para que nada se repita igual) */
function ruido(t, s) { return (Math.sin(t * 1.3 + s) + Math.sin(t * 2.1 + s * 1.7) * .6 + Math.sin(t * .7 + s * 2.3) * .4) / 2; }
var RATON = { x: -1e4, y: -1e4, t: -1e4 };
addEventListener('mousemove', function (e) { RATON.x = e.clientX; RATON.y = e.clientY; RATON.t = performance.now() / 1000; });
var TODOS = [];
function Monito(c, f, px) {
  var s = this; this.c = c; this.f = f; this.px = px;
  this.el = document.createElement('div'); this.el.className = 'mono';
  this.mini = px < 60;
  this.svg = this.mini ? NS('svg', { viewBox: '2 4 96 94', width: px, height: px * 94 / 96 }) : NS('svg', { viewBox: '-9 -24 118 133', width: px, height: px * 133 / 118 }); this.el.appendChild(this.svg);
  var uid = 'b' + Math.random().toString(36).slice(2, 8);
  this.cuerpo = NS('path', { fill: c, id: uid }); this.svg.appendChild(this.cuerpo);
  var cp = NS('clipPath', { id: uid + 'c' }), us = NS('use'); us.setAttribute('href', '#' + uid); cp.appendChild(us); this.svg.appendChild(cp);
  this.cara = NS('g', { 'clip-path': 'url(#' + uid + 'c)' }); this.svg.appendChild(this.cara);
  this.colOjo = !claro(c) && ['#3b82f6', '#8b5cf6'].indexOf(c) >= 0 ? '#ffffff' : '#231b2c';
  this.oy = f === 'pico' || f === 'nube' ? 60 : 52;
  this.ojos = [NS('rect', { rx: 3.25, fill: this.colOjo }), NS('rect', { rx: 3.25, fill: this.colOjo })];
  this.arcos = [NS('path', { fill: this.colOjo, stroke: this.colOjo, 'stroke-width': 1, 'stroke-linejoin': 'round' }), NS('path', { fill: this.colOjo, stroke: this.colOjo, 'stroke-width': 1, 'stroke-linejoin': 'round' })];
  this.ojos.concat(this.arcos).forEach(function (e) { s.cara.appendChild(e); });
  this.extra = NS('g'); this.svg.appendChild(this.extra);
  this.G = puntos(f);
  /* estado continuo */
  this.sx = 1; this.sy = 1; this.bul = 0; this.lean = 0; this.lift = 0; this.vl = 0;
  this.gx = 0; this.gy = 0; this.tgx = 0; this.tgy = 0; this.bl = 0; this.tbl = 0; this.abre = 1; this.tabre = 1;
  this.vuelta = 0; this.tvuelta = 0; this.cabeceo = 0; this.tcabeceo = 0; this.gel = new Gel(170, 7.5); this.seed = Math.random() * 100; this.cola = [];
  this.modoOjo = 'normal'; this.estado = 'libre'; this.prox = 1 + Math.random() * 2; this.antic = 0;
  this.el.addEventListener('click', function (e) { s.picar(e); });
  TODOS.push(this);
}
Monito.prototype.picar = function (e) {
  var s = this, r = this.svg.getBoundingClientRect(), lado = e.clientX < r.left + r.width / 2 ? -1 : 1, ahora = this.reloj || 0;
  this.picadas = ahora - (this.ultPicada || -9) < 1.3 ? (this.picadas || 0) + 1 : 1; this.ultPicada = ahora;
  var normal = function () { return s.estado === 'duerme' ? 'cerrado' : s.estado === 'termino' ? 'feliz' : 'normal'; };
  this.modoOjo = 'apretado'; this.sx = 1.24; this.sy = .74; this.gel.vel += -lado * 70; this.antic = 0;
  if (this.picadas >= 3) {                                                       /* cosquillas */
    for (var i = 0; i < 7; i++) (function (i) { s.cola.push([.08 * i, function () { s.gel.vel += (i % 2 ? 1 : -1) * 60; s.sy = .9; }]); })(i);
    this.cola.push([.25, function () { s.rafaga(7); }]);
    this.cola.push([.62, function () { s.modoOjo = 'feliz'; s.salta(1.15); }]);
  } else {
    this.cola.push([.2, function () { s.modoOjo = 'feliz'; s.salta(1); s.rafaga(5); }]);
  }
  this.cola.push([1.45, function () { s.modoOjo = normal(); }]);
};
/* chispas que salen disparadas desde el cuerpo en todas direcciones */
Monito.prototype.rafaga = function (n) {
  if (this.mini) return;
  var cx = 50 + this.desliza, cy = (this.G.top + this.G.base) / 2 + this.lift - 6, col = this.c === '#ffffff' ? '#dcdce6' : this.c;
  for (var i = 0; i < n; i++) {
    var a = -Math.PI / 2 + (i - (n - 1) / 2) * (Math.PI * 1.1 / n) + (Math.random() - .5) * .3, d = 52 + Math.random() * 14;
    var g = NS('g'), dentro = NS('g'); g.appendChild(dentro); GLIFO.chispa(dentro, col); g.setAttribute('transform', 'translate(' + cx.toFixed(1) + ' ' + cy.toFixed(1) + ')'); this.extra.appendChild(g);
    dentro.style.transformBox = 'fill-box'; dentro.style.transformOrigin = 'center';
    var tx = Math.cos(a) * d, ty = Math.sin(a) * d, e0 = .45 + Math.random() * .3;
    dentro.animate([{ transform: 'translate(0,0) scale(0) rotate(0deg)', opacity: 1 }, { transform: 'translate(' + tx * .75 + 'px,' + ty * .75 + 'px) scale(' + e0 + ') rotate(40deg)', opacity: 1, offset: .45 }, { transform: 'translate(' + tx + 'px,' + ty + 'px) scale(0) rotate(80deg)', opacity: 0 }],
      { duration: 700 + Math.random() * 200, easing: 'cubic-bezier(.2,.8,.3,1)', fill: 'forwards' }).onfinish = (function (g) { return function () { g.remove(); }; })(g);
  }
};
Monito.prototype.salta = function (f) { if (this.lift < -.5 || this.antic > 0) return; this.antic = .14; this.fuerza = f || 1; };
Monito.prototype.parpadea = function (doble) { var s = this; s.tbl = 1; s.cola.push([.09, function () { s.tbl = 0; }]); if (doble) s.cola.push([.26, function () { s.tbl = 1; }], [.35, function () { s.tbl = 0; }]); };
Monito.prototype.en = function (seg, fn) { this.cola.push([this.reloj + seg, fn, 1]); };
Monito.prototype.setEstado = function (st) {
  var s = this; this.estado = st; this.cola = []; while (this.extra.firstChild) this.extra.removeChild(this.extra.firstChild);
  this.modoOjo = st === 'duerme' ? 'cerrado' : st === 'termino' ? 'feliz' : 'normal'; this.prox = .3;
  this.el.style.filter = st === 'duerme' ? 'saturate(.55) brightness(.85)' : '';
  this.pensar = null;
  if (st === 'trabaja' && !this.mini) {
    var p = NS('g'), cp = this.c === '#ffffff' ? '#dcdce6' : this.c; [0, 1, 2].forEach(function (i) { p.appendChild(NS('circle', { cx: 76 + i * 11, cy: -8, r: 4.2, fill: cp })); }); this.extra.appendChild(p); this.pensar = p;
  }
  if (st === 'pregunta' && !this.mini) {
    var g = NS('g'), cg = this.c === '#ffffff' ? '#dcdce6' : this.c;
    var q = NS('g', { transform: 'translate(88 -8) scale(1.05)' }); GLIFO.pregunta(q, cg); g.appendChild(q);
    this.extra.appendChild(g); this.globo = g;
  } else this.globo = null;
};
/* ===== signos alrededor: dicen lo que siente ===== */
var GLIFO = {
  exclama: function (g, c) { g.appendChild(NS('rect', { x: -4, y: -15, width: 8, height: 19, rx: 4, fill: c })); g.appendChild(NS('circle', { cx: 0, cy: 10.5, r: 4.3, fill: c })); },
  pregunta: function (g, c) { g.appendChild(NS('path', { d: 'M-6.5 -7C-6.5 -14.5 6.5 -14.5 6.5 -7 6.5 -2 0 -1.5 0 3.5', stroke: c, 'stroke-width': 6, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })); g.appendChild(NS('circle', { cx: 0, cy: 11.5, r: 3.8, fill: c })); },
  nota: function (g, c) { g.appendChild(NS('ellipse', { cx: -3, cy: 9, rx: 6.5, ry: 5, fill: c, transform: 'rotate(-18 -3 9)' })); g.appendChild(NS('rect', { x: 1.5, y: -13, width: 4, height: 22, rx: 2, fill: c })); g.appendChild(NS('path', { d: 'M3.5 -13C10 -12 13 -8 12 -2 10 -5.5 7.5 -7 3.5 -7Z', fill: c })); },
  chispa: function (g, c) { g.appendChild(NS('path', { d: 'M0 -13C1.6 -4.5 4.5 -1.6 13 0 4.5 1.6 1.6 4.5 0 13 -1.6 4.5 -4.5 1.6 -13 0 -4.5 -1.6 -1.6 -4.5 0 -13Z', fill: c, 'stroke-linejoin': 'round', stroke: c, 'stroke-width': 1.5 })); },
  gota: function (g, c) { g.appendChild(NS('path', { d: 'M0 -12C0 -12 9 -2 9 4 9 9.5 5 13 0 13S-9 9.5 -9 4C-9 -2 0 -12 0 -12Z', fill: '#8fd3ff' })); },
  enojo: function (g, c) { [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(function (q) { g.appendChild(NS('path', { d: 'M' + (q[0] * 3) + ' ' + (q[1] * 11) + 'Q' + (q[0] * 3) + ' ' + (q[1] * 3) + ' ' + (q[0] * 11) + ' ' + (q[1] * 3), stroke: c, 'stroke-width': 5, fill: 'none', 'stroke-linecap': 'round' })); }); },
  idea: function (g, c) { [[-15, -3, -11, -2], [15, -3, 11, -2], [0, -19, 0, -15], [-11, -14, -8, -11], [11, -14, 8, -11]].forEach(function (l) { g.appendChild(NS('path', { d: 'M' + l[0] + ' ' + l[1] + 'L' + l[2] + ' ' + l[3], stroke: '#ffd84d', 'stroke-width': 3.6, 'stroke-linecap': 'round' })); }); g.appendChild(NS('circle', { cx: 0, cy: -2, r: 9, fill: '#ffd84d' })); g.appendChild(NS('rect', { x: -5, y: 6, width: 10, height: 6, rx: 3, fill: '#d6d6e0' })); },
  check: function (g, c) { g.appendChild(NS('circle', { cx: 0, cy: 0, r: 12, fill: c })); g.appendChild(NS('path', { d: 'M-5.5 .5L-1.5 4.5 6 -4', stroke: '#fff', 'stroke-width': 4, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })); },
  palomita: function (g, c) { g.appendChild(NS('path', { d: 'M-8 0L-2.5 5.5 9 -6.5', stroke: c, 'stroke-width': 5.5, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })); },
  lineas: function (g, c) { [[0, -14, 0, -6], [-11, -9, -6, -4], [11, -9, 6, -4]].forEach(function (l) { g.appendChild(NS('path', { d: 'M' + l[0] + ' ' + l[1] + 'L' + l[2] + ' ' + l[3], stroke: c, 'stroke-width': 4.5, 'stroke-linecap': 'round' })); }); },
  z: function (g, c, tam) { var k = (tam || 14) / 14; g.appendChild(NS('path', { d: 'M' + (-6 * k) + ' ' + (-6 * k) + 'H' + (6 * k) + 'L' + (-6 * k) + ' ' + (6 * k) + 'H' + (6 * k), stroke: c, 'stroke-width': 3.8 * k, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })); }
};
/* aparece con un pop, flota y se desvanece; «donde»: arriba-der, arriba-izq, arriba o al lado */
Monito.prototype.signo = function (tipo, o) {
  if (this.mini) return;
  o = o || {}; var G = this.G, top = G.top + this.lift, lado = o.lado || (Math.random() < .5 ? 1 : -1);
  var pos = { der: [88, top - 2], izq: [12, top - 2], arriba: [50 + this.lean, top - 20], cara: [50 + lado * 40, this.oy - 6] }[o.donde || 'der'];
  var x = pos[0] + (o.dx || 0), y = pos[1] + (o.dy || 0), g = NS('g'), dentro = NS('g'); g.appendChild(dentro); GLIFO[tipo](dentro, o.color || (this.c === '#ffffff' ? '#dcdce6' : this.c), o.tam);
  g.setAttribute('transform', 'translate(' + x.toFixed(1) + ' ' + y.toFixed(1) + ')'); this.extra.appendChild(g);
  var esc = (o.esc || 1) * 1.05, sube = o.sube == null ? 14 : o.sube, dur = o.dur || 1500, ladeo = o.ladeo == null ? (Math.random() - .5) * 24 : o.ladeo;
  dentro.style.transformBox = 'fill-box'; dentro.style.transformOrigin = 'center';
  dentro.animate([{ transform: 'translate(0,0) scale(0) rotate(' + (-ladeo) + 'deg)', opacity: 0 }, { transform: 'translate(0,-3px) scale(' + (1.18 * esc) + ') rotate(' + ladeo * .5 + 'deg)', opacity: 1, offset: .14 },
    { transform: 'translate(0,-5px) scale(' + esc + ') rotate(0deg)', opacity: 1, offset: .3 }, { transform: 'translate(' + (lado * 3) + 'px,' + (-sube) + 'px) scale(' + (esc * .9) + ') rotate(' + ladeo * .4 + 'deg)', opacity: 0 }],
    { duration: dur, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'forwards' }).onfinish = function () { g.remove(); };
};
Monito.prototype.racha = function (tipo, n, sep, o) { var s = this; for (var i = 0; i < n; i++) (function (i) { s.cola.push([i * sep, function () { s.signo(tipo, Object.assign({}, o || {}, { dx: (Math.random() - .5) * 14, dy: (Math.random() - .5) * 6 })); }]); })(i); };

/* ===== qué hace por su cuenta ===== */
Monito.prototype.decide = function () {
  var s = this, st = this.estado, r = Math.random();
  if (st === 'libre') {
    var normal = function () { if (s.estado === 'libre') s.modoOjo = 'normal'; };
    var gestos = this.mini ? ['mira', 'mira', 'brinco', 'brinco', 'asiente', 'niega', 'sacude', 'vuelta', 'alrededor', 'parpadea', 'brillo', 'suspira', 'cabecea'] : ['parpadea', 'parpadea', 'mira', 'mira', 'tararea', 'curioso', 'brillo', 'brinco', 'asiente', 'niega', 'sacude', 'suspira', 'cabecea', 'alrededor', 'vuelta'];
    var gs = gestos[Math.floor(r * gestos.length)];
    if (gs === 'parpadea') this.parpadea(Math.random() < .2);
    if (gs === 'mira') { this.tgx = (Math.random() < .5 ? -1 : 1) * (3 + Math.random() * 3.5); this.tgy = (Math.random() - .6) * 4.5; this.volver = this.reloj + .8 + Math.random() * 1.6; }
    if (gs === 'tararea') { this.gel.vel += (Math.random() < .5 ? -1 : 1) * 42; this.tabre = .82; this.en(1.6, function () { s.tabre = 1; }); this.racha('nota', 2, .55, { donde: 'der', sube: 18 }); }
    if (gs === 'curioso') { this.tgx = 4; this.tgy = -3.5; this.signo('pregunta', { donde: 'der', esc: .8 }); this.volver = this.reloj + 1.6; }
    if (gs === 'brillo') { this.modoOjo = 'feliz'; this.en(1.1, normal); this.racha('chispa', 2, .25, { donde: Math.random() < .5 ? 'der' : 'izq', esc: .75 }); }
    if (gs === 'brinco') this.salta(.8 + Math.random() * .3);
    if (gs === 'asiente') { [0, .22, .44, .66].forEach(function (d, i) { s.cola.push([d, function () { s.tcabeceo = i % 2 ? 0 : 3.2; s.sy = i % 2 ? 1.02 : .95; }]); }); s.cola.push([.88, function () { s.tcabeceo = 0; }]); }
    if (gs === 'niega') { [0, .18, .36, .54].forEach(function (d, i) { s.cola.push([d, function () { s.tgx = i % 2 ? 4 : -4; s.gel.vel += (i % 2 ? 1 : -1) * 18; }]); }); s.cola.push([.72, function () { s.tgx = 0; }]); }
    if (gs === 'sacude') { this.modoOjo = 'apretado'; for (var i = 0; i < 8; i++) (function (i) { s.cola.push([.06 * i, function () { s.gel.vel += (i % 2 ? 1 : -1) * 70; }]); })(i); s.cola.push([.6, normal]); }
    if (gs === 'suspira') { this.tabre = .55; this.cola.push([0, function () { s.sx = .96; s.sy = 1.09; }]); this.cola.push([.7, function () { s.sx = 1.08; s.sy = .9; }]); this.cola.push([1.3, function () { s.tabre = 1; }]); }
    if (gs === 'cabecea') { this.tabre = .35; this.tcabeceo = 2.5; this.cola.push([1.1, function () { s.tcabeceo = 4.5; }]); this.cola.push([1.5, function () { s.tabre = 1.15; s.tcabeceo = 0; s.salta(.45); s.signo('exclama', { donde: 'der', esc: .7, sube: 6, dur: 800 }); }]); this.cola.push([1.9, function () { s.tabre = 1; }]); }
    if (gs === 'alrededor') { this.tgx = -5.5; this.tgy = -1; this.cola.push([.7, function () { s.tgx = 5.5; }]); this.cola.push([1.5, function () { s.tgx = 0; s.tgy = 0; }]); }
    if (gs === 'vuelta') { this.tvuelta = 40; this.cola.push([.55, function () { s.vuelta = -40; s.tvuelta = 0; }]); }
    this.prox = this.reloj + 1 + Math.random() * 1.8;
  } else if (st === 'trabaja') {
    /* lee: saltos cortos de izquierda a derecha y regreso rápido */
    this.leyendo = (this.leyendo || 0) + 1;
    var kl = this.mini ? 1.6 : 1; if (this.leyendo % 5 === 0) { this.tgx = -3 * kl; this.tgy = 1.6 * kl; } else { this.tgx = Math.min(3 * kl, this.tgx + 1.5 * kl); this.tgy = 1.6 * kl; }
    if (Math.random() < .12) this.parpadea();
    if (Math.random() < .05) this.salta(.35);
    this.prox = this.reloj + .28 + Math.random() * .2;
  } else if (st === 'pregunta') {
    if (r < .35) { this.salta(.75); this.signo('lineas', { donde: 'izq', sube: 4, dur: 900 }); } else if (r < .7) this.parpadea(); else { this.gel.vel += 22; this.signo('exclama', { donde: 'izq', esc: .75, sube: 8 }); }
    this.prox = this.reloj + 1.4 + Math.random() * 1.2;
  } else if (st === 'termino') {
    this.salta(.85);
    this.signo('palomita', { donde: 'der', sube: 8, dur: 2000 });
    this.prox = this.reloj + 4.5;
  } else if (st === 'error') {
    [0, .09, .18, .27].forEach(function (d, i) { s.en(d, function () { s.gel.vel += (i % 2 ? 1 : -1) * 55; }); });
    this.tabre = .7; this.tgy = 2;
    this.signo(Math.random() < .55 ? 'gota' : 'enojo', { donde: 'der', sube: Math.random() < .5 ? -8 : 10, dur: 1600 });
    this.prox = this.reloj + 3.4;
  } else if (st === 'duerme') {
    this.signo('z', { donde: 'der', sube: 20, dur: 3000, tam: 10 + Math.random() * 6, ladeo: 12, lado: 1 });
    this.prox = this.reloj + 1.5;
  }
};
/* ===== cada cuadro ===== */
Monito.prototype.paso = function (dt, t) {
  var s = this, st = this.estado; this.reloj = t;
  if (this.quieto) { this.prox = t + 99; }
  this.cola = this.cola.filter(function (c) { if (c[2]) { if (t >= c[0]) { c[1](); return false; } return true; } c[0] -= dt; if (c[0] <= 0) { c[1](); return false; } return true; });
  if (t >= this.prox) this.decide();
  if (this.volver && t > this.volver) { this.tgx = 0; this.tgy = 0; this.volver = 0; }
  /* te ve: si el cursor anda cerca, lo sigue con los ojos y se inclina hacia él */
  var vista = t - RATON.t < 2.5 && st !== 'duerme' && !this.quieto;
  if (vista) {
    var r = this.svg.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height * .45, dx = RATON.x - cx, dy = RATON.y - cy, dist = Math.hypot(dx, dy);
    if (dist < 1400) { var k = Math.min(1, dist / 110); this.tgx = dx / (dist || 1) * 6.5 * k; this.tgy = dy / (dist || 1) * 4.6 * k; }
    var cerca = dist < r.width * .9;
    if (cerca && !this.cerca && st !== 'duerme') { this.tabre = 1.22; this.salta(.95); this.signo('exclama', { donde: 'der', sube: 10, dur: 1100 }); this.en(.7, function () { s.tabre = 1; }); }
    this.cerca = cerca;
  }
  /* respirar: lento y con algo de ruido para que no parezca máquina */
  var resp = { libre: [1.5, .026], trabaja: [3.2, .022], pregunta: [1.8, .026], termino: [1.6, .026], error: [1.2, .016], duerme: [.75, .045] }[st];
  var b = Math.sin((t + this.seed) * resp[0] * Math.PI) + ruido(t * .6, this.seed) * .35;
  var A = this.mini ? 1.8 : 1, tsx = 1 - resp[1] * A * .7 * b, tsy = 1 + resp[1] * A * b, tbul = resp[1] * A * .9 * b;
  if (st === 'duerme') { tsx += .03; tsy -= .03; }
  /* el salto: se agacha, despega estirado, cae y se aplasta */
  if (this.antic > 0) { this.antic -= dt; tsx = 1.15; tsy = .82; if (this.antic <= 0) { this.vl = -195 * this.fuerza; } }
  if (this.lift < 0 || this.vl < 0) {
    this.vl += 980 * dt; this.lift += this.vl * dt; tsx = 1 - Math.min(.1, Math.abs(this.vl) / 2000); tsy = 1 + Math.min(.13, Math.abs(this.vl) / 1500);
    if (this.lift >= 0) { var imp = Math.min(1, this.vl / 160); this.lift = 0; this.vl = 0; this.sx = 1 + .18 * imp; this.sy = 1 - .2 * imp; this.gel.vel += (Math.random() - .5) * 30 * imp; }
  }
  this.sx = hacia(this.sx, tsx, 9, dt); this.sy = hacia(this.sy, tsy, 9, dt); this.bul = hacia(this.bul, tbul, 6, dt);
  /* los ojos: saltan rápido a su objetivo (como los de verdad) y el cuerpo los sigue despacio */
  if (!this.mic || t > this.mic) { this.mx = (Math.random() - .5) * .7; this.my = (Math.random() - .5) * .5; this.mic = t + .25 + Math.random() * .5; }
  this.gx = hacia(this.gx, this.tgx + this.mx, 22, dt); this.gy = hacia(this.gy, this.tgy + this.my, 22, dt);
  this.lean = hacia(this.lean, this.gx * (this.mini ? 2.4 : 1.7) + ruido(t * .5, this.seed + 3) * (this.mini ? 1.8 : 1.1) + (st === 'pregunta' ? (this.mini ? 6 : 3) : 0), 4.2, dt);
  this.desliza = hacia(this.desliza || 0, this.gx * .75, 4, dt);
  this.gel.paso(dt);
  this.bl = hacia(this.bl, this.tbl, 38, dt); this.abre = hacia(this.abre, this.tabre, 12, dt);
  this.vuelta = hacia(this.vuelta, this.tvuelta, 7, dt); this.cabeceo = hacia(this.cabeceo, this.tcabeceo, 8, dt);
  /* deformar la silueta: la base queda en el piso, la parte de arriba se mece y se aplasta */
  var G = this.G, base = G.base, H = base - G.top, sx = this.sx, sy = this.sy, bul = this.bul, lean = this.lean + this.gel.v, lift = this.lift, f = this.f;
  var ang = (this.lean + this.gel.v * .6) * .011, co = Math.cos(ang), si = Math.sin(ang), jel = this.gel.v * .25;
  function def(x, y) {
    var h = Math.max(0, Math.min(1, (base - y) / H));
    var ex = sx * (1 + bul * Math.sin(Math.PI * h));
    var dx = (x - 50) * ex, dy = -(base - y) * sy;
    var X = 50 + dx * co - dy * si + s.desliza + jel * h * h, Y = base + dx * si + dy * co + lift;
    if (f === 'fantasma' && h < .14) Y += Math.sin(x * .32 + t * 4.2) * 1.4 * (1 - h / .14);
    if (f === 'gatito' && y < 24) X += Math.sin(t * 2.4 + (x < 50 ? 0 : 1.7)) * .6 * (24 - y) / 16;
    return [X, Y];
  }
  this.cuerpo.setAttribute('d', curva(G.pts.map(function (p) { return def(p[0], p[1]); })));
  /* la carita, pegada al cuerpo deformado */
  var oy = this.oy, ab = this.abre;
  var giro = Math.max(-1, Math.min(1, s.gx / 6.5));
  [40.6, 61.9].forEach(function (cx, i) {
    var lado = i === 0 ? -1 : 1, junta = -lado * Math.abs(giro) * .8;
    var c = def(cx + s.gx + junta + s.vuelta, oy - 1.5 + s.gy + s.cabeceo), crece = ab > 1 ? 1 + (ab - 1) * .45 : 1, cierra = ab < 1 ? ab : 1, w = 7.4 * crece, hgt = 16.8 * crece * cierra * (1 - .9 * s.bl);
    var o = s.ojos[i], a = s.arcos[i];
    if (s.modoOjo === 'normal') {
      o.style.display = ''; a.style.display = 'none';
      o.setAttribute('x', (c[0] - w / 2).toFixed(2)); o.setAttribute('y', (c[1] - hgt / 2).toFixed(2)); o.setAttribute('width', w.toFixed(2)); o.setAttribute('height', Math.max(1.6, hgt).toFixed(2)); o.setAttribute('rx', Math.min(w / 2, hgt / 2).toFixed(2));
    } else {
      o.style.display = 'none'; a.style.display = '';
      var X = c[0], Y = c[1];
      if (s.modoOjo === 'apretado') { var k = i === 0 ? 1 : -1; a.setAttribute('d', 'M' + (X - 4.6 * k) + ' ' + (Y - 6.2) + 'L' + (X + 4.4 * k) + ' ' + (Y - .9) + 'Q' + (X + 5.6 * k) + ' ' + Y + ' ' + (X + 4.4 * k) + ' ' + (Y + .9) + 'L' + (X - 4.6 * k) + ' ' + (Y + 6.2) + 'L' + (X - 2.6 * k) + ' ' + (Y + 3) + 'L' + (X + 1 * k) + ' ' + Y + 'L' + (X - 2.6 * k) + ' ' + (Y - 3) + 'Z'); }
      else if (s.modoOjo === 'feliz') { a.setAttribute('d', 'M' + (X - 6) + ' ' + (Y + 3.4) + 'Q' + X + ' ' + (Y - 9.5) + ' ' + (X + 6) + ' ' + (Y + 3.4) + 'Q' + (X + 6.4) + ' ' + (Y + 5.8) + ' ' + (X + 3.6) + ' ' + (Y + 5.2) + 'Q' + X + ' ' + (Y - .6) + ' ' + (X - 3.6) + ' ' + (Y + 5.2) + 'Q' + (X - 6.2) + ' ' + (Y + 5.4) + ' ' + (X - 6) + ' ' + (Y + 3.4) + 'Z'); }
      else { a.setAttribute('d', 'M' + (X - 6) + ' ' + (Y - .6) + 'Q' + X + ' ' + (Y + 7.5) + ' ' + (X + 6) + ' ' + (Y - .6) + 'Q' + (X + 6.2) + ' ' + (Y - 2.6) + ' ' + (X + 4.2) + ' ' + (Y - 2.2) + 'Q' + X + ' ' + (Y + 1.6) + ' ' + (X - 3.8) + ' ' + (Y - 2.4) + 'Q' + (X - 6.2) + ' ' + (Y - 2.6) + ' ' + (X - 6) + ' ' + (Y - .6) + 'Z'); }
    }
  });
  if (this.pensar) [].forEach.call(this.pensar.childNodes, function (cn, i) { var a = Math.max(0, Math.sin(t * 4.5 - i * .9)); cn.setAttribute('opacity', (.25 + .75 * a).toFixed(2)); cn.setAttribute('transform', 'translate(' + (lean * .5).toFixed(2) + ' ' + (lift - 2.5 * a).toFixed(2) + ')'); });
  if (this.globo) this.globo.setAttribute('transform', 'translate(' + (lean * .6).toFixed(2) + ' ' + (Math.sin(t * 2.4) * 3 + lift).toFixed(2) + ') rotate(' + (Math.sin(t * 1.7) * 9).toFixed(2) + ' 88 -8)');
};
var ANT = performance.now();
function tic(ahora) {
  var dt = Math.min(.04, (ahora - ANT) / 1000); ANT = ahora;
  TODOS = TODOS.filter(function (m) { return m.el.isConnected; });
  TODOS.forEach(function (m) { m.paso(dt, ahora / 1000); });
  requestAnimationFrame(tic);
}
requestAnimationFrame(tic);

