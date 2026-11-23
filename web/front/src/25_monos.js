/* ================= puente con los monitos =================
   Cada lugar (barra, píldora, panel, tarjeta…) pide el monito de un agente; se reusa para que su animación no arranque
   de cero en cada repintado. Si cambian su forma, color o tamaño, se crea otro. */
var FORMAS = FORMAS6.slice();
var COLORES = COLS.slice();
var NOMBRES_FORMA = { bolita: 'Bolita', pico: 'Pico', cuadrito: 'Cuadrito', gatito: 'Gatito', fantasma: 'Fantasmita', nube: 'Nubecita' };
var MONOS = {};
function monitoDe(lugar, a, px) {
  var k = lugar + '|' + a.id, m = MONOS[k], st = estadoDe(a), f = FORMAS.indexOf(a.f) >= 0 ? a.f : 'bolita';
  if (!m || m.c !== a.c || m.f !== f || m.px !== px) { m = MONOS[k] = new Monito(a.c, f, px); m.setEstado(st); }
  else {
    if (m.estado !== st) m.setEstado(st);
    /* el reloj saca de TODOS a los que salieron de pantalla; al volver hay que darlo de alta otra vez o se congela */
    if (TODOS.indexOf(m) < 0) TODOS.push(m);
  }
  return m.el;
}
function monoObj(lugar, a) { return MONOS[lugar + '|' + a.id]; }
/* monito suelto (vista previa, botones de forma): los de los botones van quietos */
function monito(c, f, px, opts) {
  var m = new Monito(c, FORMAS.indexOf(f) >= 0 ? f : 'bolita', px);
  m.setEstado((opts && opts.estado) || 'libre');
  if (opts && opts.quieto) m.quieto = true;
  return m.el;
}
/* qué está haciendo: de aquí salen el estado del monito, la rayita y el «Ahora» del resumen */
var TXT_ACT = { enviando: 'enviando tu mensaje', recibido: 'lo recibió', pensando: 'pensando', leyendo: 'leyendo', escribiendo: 'escribiendo', skill: 'corriendo una skill', espera: 'te espera', listo: 'terminó', error: 'algo falló', cambiando: 'cambiando de motor', cerrado: 'se cerró su motor', no_salio: 'no se mandó', dormido: 'dormido', libre: 'libre' };
var ESTADO_DE_ACT = { enviando: 'trabaja', recibido: 'trabaja', pensando: 'trabaja', leyendo: 'trabaja', escribiendo: 'trabaja', skill: 'trabaja', espera: 'pregunta', listo: 'termino', error: 'error', cambiando: 'trabaja', cerrado: 'error', no_salio: 'error', dormido: 'duerme', libre: 'libre' };
function estadoDe(a) { return ESTADO_DE_ACT[actividadDe(a).k] || 'libre'; }
function rayita(a) {
  var x = actividadDe(a), r = el('i', 'ray7 r-' + x.k);
  if (x.k === 'pensando') for (var i = 0; i < 3; i++) r.appendChild(el('b'));
  if (x.k === 'skill') for (var j = 0; j < x.n; j++) r.appendChild(el('b', j < x.p ? 'h' : j === x.p ? 'a' : ''));
  return r;
}
function textoAct(a) { var x = actividadDe(a); return TXT_ACT[x.k] + (x.k === 'skill' && x.n ? ' · paso ' + (x.p + 1) + ' de ' + x.n : ''); }
