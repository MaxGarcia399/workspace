/* ================= la página para gente que no sabe de terminal =================
   Cuando su motor tiene un problema (sin sesión, sin créditos, sin instalar, una versión vieja, sin internet), una
   tarjeta lo dice en simple: qué pasó, qué está haciendo Workspace y UN botón grande. El detalle técnico va en
   «Ver detalle», cerrado. Lo que se arregla solo (entrar a su cuenta con su ventana oficial, actualizarlo) se ve
   avanzar aquí y, al terminar, tu mensaje sale solo. Si hace falta la terminal (entrar a tu cuenta), Workspace la
   abre sola y aquí va la guía con dibujos; nunca pide escribir comandos (si es inevitable, «Copiar»). */
var AMI_TXT = {
  sin_sesion: { t: '{m} necesita que vuelvas a entrar a tu cuenta', p: 'Es normal: cada tanto la sesión se vence. Te abro una ventana para entrar y sigo solo cuando termines.' },
  sin_creditos: { t: '{m} se quedó sin créditos por ahora', p: 'No hiciste nada mal: tu plan llegó a su límite.' },
  actualizar: { t: 'Estoy poniendo al día {m}', p: 'Su versión ya no funciona bien con Workspace. Lo actualizo solo y, cuando termine, sigo con tu mensaje.' },
  sin_instalar: { t: '{m} no está instalado en esta computadora', p: 'Puedo instalarlo por ti: tarda un par de minutos y no tienes que hacer nada.' },
  sin_internet: { t: 'Parece que no hay internet', p: 'Revisa tu wifi o tu cable. En cuanto vuelva, lo intento de nuevo.' }
};
/* qué ve la persona al entrar a su cuenta, por motor: [dibujo, texto] */
var AMI_GUIA = {
  'claude-code': [['ventana', 'Se abrió una ventana de la terminal y, enseguida, tu navegador.'], ['cuenta', 'En el navegador, entra con tu cuenta de Claude y pulsa «Autorizar».'], ['listo', 'Vuelve aquí: me doy cuenta solo y sigo con tu mensaje.']],
  codex: [['ventana', 'Se abrió una ventana de la terminal y, enseguida, tu navegador.'], ['cuenta', 'En el navegador, entra con tu cuenta de ChatGPT y acepta.'], ['listo', 'Vuelve aquí: me doy cuenta solo y sigo con tu mensaje.']],
  copilot: [['ventana', 'Se abrió una ventana de la terminal. Si te muestra un código (como ABCD-1234), déjala abierta.'], ['codigo', 'En tu navegador, entra a github.com/login/device, escribe ese código y pulsa «Authorize».'], ['listo', 'Vuelve aquí: me doy cuenta solo y sigo con tu mensaje.']]
};
var AMI_GUIA_OTRO = [['ventana', 'Se abrió una ventana para entrar a tu cuenta de {m}.'], ['cuenta', 'Sigue lo que te pide (casi siempre, entrar con tu cuenta en el navegador).'], ['listo', 'Vuelve aquí: me doy cuenta solo y sigo con tu mensaje.']];
/* los dibujos de la guía: lo que van a ver, en trazos simples */
function amiDibujo(k) {
  var s = NS('svg', { width: 64, height: 44, viewBox: '0 0 64 44', fill: 'none', 'class': 'dib' });
  function r(x, y, w, h, c, f) { s.appendChild(NS('rect', { x: x, y: y, width: w, height: h, rx: 4, stroke: c || '#6f6f78', 'stroke-width': 1.6, fill: f || 'none' })); }
  function l(x1, y1, x2, y2, c) { s.appendChild(NS('line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: c || '#a4a4ad', 'stroke-width': 1.8, 'stroke-linecap': 'round' })); }
  if (k === 'ventana') { r(2, 4, 44, 32, '#6f6f78', '#19191c'); l(8, 14, 12, 18, '#3fbf7f'); l(12, 18, 8, 22, '#3fbf7f'); l(16, 22, 30, 22); r(30, 14, 32, 26, '#a4a4ad', '#202024'); l(36, 22, 56, 22); l(36, 28, 50, 28); }
  else if (k === 'cuenta') { r(4, 4, 56, 36, '#a4a4ad', '#202024'); l(4, 12, 60, 12, '#6f6f78'); s.appendChild(NS('circle', { cx: 32, cy: 22, r: 4, stroke: '#a4a4ad', 'stroke-width': 1.6 })); r(20, 29, 24, 7, '#3fbf7f', '#3fbf7f'); }
  else if (k === 'codigo') { r(4, 4, 56, 36, '#a4a4ad', '#202024'); l(4, 12, 60, 12, '#6f6f78'); [10, 20, 30, 40].forEach(function (x) { r(x, 20, 8, 10, '#e7a43a'); }); r(18, 33, 28, 5, '#3fbf7f', '#3fbf7f'); }
  else if (k === 'escribe') { r(2, 4, 60, 36, '#6f6f78', '#19191c'); l(8, 16, 12, 20, '#3fbf7f'); l(12, 20, 8, 24, '#3fbf7f'); r(16, 15, 22, 10, '#e7a43a'); s.appendChild(NS('path', { d: 'M54 13v9h-9', stroke: '#a4a4ad', 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })); l(45, 22, 48, 19); l(45, 22, 48, 25); }
  else if (k === 'confia') { r(4, 4, 56, 36, '#a4a4ad', '#202024'); [13, 22, 31].forEach(function (y) { s.appendChild(NS('path', { d: 'M10 ' + y + 'l3 3 6-6', stroke: '#3fbf7f', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })); l(24, y, 52, y); }); }
  else { s.appendChild(NS('circle', { cx: 32, cy: 22, r: 16, stroke: '#3fbf7f', 'stroke-width': 2.2 })); s.appendChild(NS('path', { d: 'M24 22l6 6 11-12', stroke: '#3fbf7f', 'stroke-width': 2.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })); }
  return s;
}
/* `pasos`: otra guía que la de entrar a la cuenta (la de confiar en los hooks de Codex) */
function amiGuia(motor, m, pasos) {
  var ol = el('ol', 'guia');
  (pasos || AMI_GUIA[motor] || AMI_GUIA_OTRO).forEach(function (p, i) {
    var li = el('li'); li.appendChild(el('span', 'n', String(i + 1))); li.appendChild(amiDibujo(p[0])); li.appendChild(amiTexto(p[1], m)); ol.appendChild(li);
  });
  return ol;
}
/* el texto de un paso; lo que hay que escribir, en su tecla: ['Escribe ', {k: '/hooks'}, ' y pulsa Enter.'] */
function amiTexto(x, m) {
  if (typeof x === 'string') return el('span', null, x.replace('{m}', m));
  var s = el('span');
  x.forEach(function (p) { s.appendChild(typeof p === 'string' ? el('span', null, p.replace('{m}', m)) : el('kbd', null, p.k)); });
  return s;
}
function amiArreglar(a, accion, b) {
  if (b) b.disabled = true;
  return post('/api/v2/arreglar', { agente: a.id, accion: accion }).then(function (r) {
    if (accion === 'seguir_con' && r && r.motor) nota('Sigo con ' + motorN(r.motor) + (r.manda ? ': tu mensaje ya va para allá' : ''));
    if (b) b.disabled = false; acelerar(); return r;
  }, function (x) { nota(x.message, true); if (b) b.disabled = false; });
}
function amiBoton(t, run) { var b = el('button', 'grande', t); b.onclick = function (ev) { ev.stopPropagation(); run(b); }; return b; }
/* lo que está haciendo Workspace ahora (una línea, con su ruedita mientras trabaja) */
function amiHace(t, gira) { var h = el('div', 'hace'); if (gira) h.appendChild(el('i')); h.appendChild(el('span', null, t)); return h; }
function amiDetalle(textos) {
  var t = textos.filter(function (x) { return x; }).join('\n\n');
  if (!t) return null;
  var d = el('details', 'vd'); d.appendChild(el('summary', null, 'Ver detalle')); d.appendChild(el('pre', null, t)); return d;
}
/* sin internet: lo intenta de nuevo solo, una vez, a los AMI_RED_S */
var AMI_RED_S = 20;
function amiReintentoRed(a, e) {
  var l = L(a), ultimo = ultimoMio(a);
  if (!ultimo || (l.amiRed && l.amiRed.texto === e.texto)) return;
  l.amiRed = { texto: e.texto, t: Date.now() };
  setTimeout(function () { if (L(a).amiRed && L(a).amiRed.texto === e.texto && errorDe(a) && errorDe(a).texto === e.texto) { L(a).errCerrado = e.texto; amiArreglar(a, 'reintentar'); } }, AMI_RED_S * 1000);
}
/* la tarjeta de un motor con problemas: `e` el error de su foto (con su `estado`), `ar` lo que Workspace está arreglando */
function tarjetaAmigable(a, e, ar) {
  var motor = e.motor || motorChat(a), m = motorN(motor), est = e.estado, tx = AMI_TXT[est] || AMI_TXT.sin_sesion;
  var alt = e.alternativa, A = alt ? motorN(alt) : '';
  if (ar && ar.motor !== motor) ar = null;
  var c = el('div', 'ami' + (ar && ar.paso === 'listo' ? ' ok' : '')), mo = el('div', 'mono'); mo.appendChild(monitoDe('ami', a, 44)); c.appendChild(mo);
  var t = el('div', 'tx'), titulo = tx.t.replace('{m}', m), parrafo = tx.p, boton = null, detalle = [e.texto];
  var paso = ar ? ar.paso : '';
  if (est === 'sin_creditos') {
    parrafo += alt ? ' Puedes seguir esta misma conversación con ' + A + ': ya sabe de qué hablaban.' : ' Cuando recargues tu cuenta de ' + m + ' (o se renueve tu plan), vuelve a mandar tu mensaje.';
    boton = alt ? amiBoton('Seguir con ' + A, function (b) { amiArreglar(a, 'seguir_con', b); }) : amiBoton('Volver a intentarlo', function () { var u = ultimoMio(a); L(a).errCerrado = e.texto; if (u) amiArreglar(a, 'reintentar'); });
  }
  t.appendChild(el('b', 't', titulo)); t.appendChild(el('p', null, parrafo));
  if (est === 'sin_sesion') {
    if (paso === 'listo') t.appendChild(amiHace('¡Listo! Ya entraste. Sigo con tu mensaje.'));
    else if (paso === 'abriendo') t.appendChild(amiHace('Abriendo la ventana para entrar…', true));
    else if (paso === 'esperando') {
      t.appendChild(amiGuia(motor, m));
      var d = dondeTerminal(ar.donde);
      t.appendChild(amiHace('Te espero' + (d ? ' (la ventana está en la ' + d + ' del hub)' : '') + '…', true));
    } else if (paso === 'sin_herdr') {
      t.appendChild(el('p', null, 'No encontré dónde abrir la ventana para entrar. Abre la terminal, pega esto y sigue lo que te pida:'));
      (ar.comandos || []).forEach(function (cmd) {
        var x = cmd.replace(/^\$ /, ''), f = el('div', 'cmd'); f.appendChild(el('code', null, x));
        f.appendChild(amiBotonChico('Copiar', function () { amiCopiar(x); })); t.appendChild(f);
      });
      t.appendChild(amiGuia(motor, m));
    } else {
      if (paso === 'sin_terminar') t.appendChild(el('p', 'ojo', 'Parece que no terminaste de entrar. ¿Lo intentamos otra vez?'));
      if (paso === 'fallo') { t.appendChild(el('p', 'ojo', 'No pude abrir la ventana para entrar.')); detalle.push(ar.detalle); }
      boton = amiBoton(paso ? 'Abrir la ventana otra vez' : 'Entrar a mi cuenta', function (b) { amiArreglar(a, 'iniciar_sesion', b); });
    }
  } else if (est === 'actualizar' || est === 'sin_instalar') {
    var accion = est === 'actualizar' ? 'actualizar' : 'instalar';
    if (paso === 'trabajando') t.appendChild(amiHace((est === 'actualizar' ? 'Actualizando ' : 'Instalando ') + m + '… no tienes que hacer nada.', true));
    else if (paso === 'listo') t.appendChild(amiHace('¡Listo! ' + m + (est === 'actualizar' ? ' ya está al día.' : ' ya está instalado.') + ' Sigo con tu mensaje.'));
    else {
      if (paso === 'fallo') { t.appendChild(el('p', 'ojo', 'No pude ' + (est === 'actualizar' ? 'actualizarlo' : 'instalarlo') + ' solo.')); detalle.push(ar.detalle); }
      boton = alt && paso === 'fallo' ? amiBoton('Seguir con ' + A, function (b) { amiArreglar(a, 'seguir_con', b); })
        : amiBoton(paso === 'fallo' ? 'Intentarlo otra vez' : (est === 'actualizar' ? 'Actualizar ' + m : 'Instalar ' + m), function (b) { amiArreglar(a, accion, b); });
    }
  } else if (est === 'sin_internet') {
    amiReintentoRed(a, e);
    t.appendChild(amiHace('Lo intento de nuevo solo en unos segundos…', true));
    boton = amiBoton('Intentarlo ya', function () { var u = ultimoMio(a); L(a).errCerrado = e.texto; L(a).amiRed = null; if (u) amiArreglar(a, 'reintentar'); });
  }
  if (boton) t.appendChild(boton);
  var vd = amiDetalle(detalle); if (vd) t.appendChild(vd);
  c.appendChild(t);
  return c;
}
function amiBotonChico(t, run) { var b = el('button', 'chip', t); b.onclick = function (ev) { ev.stopPropagation(); run(b); }; return b; }
function amiCopiar(x) {
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(x).then(function () { nota('Copiado'); }, function () { nota('No pude copiarlo: selecciónalo y cópialo', true); });
  else nota('No pude copiarlo: selecciónalo y cópialo', true);
}
/* lo que Workspace hizo solo, en una línea y con su deshacer */
function piezaAvisoAmigable(a, av) {
  var m = motorN(av.motor || motorChat(a)), w = el('div', 'aviso ami-av');
  w.appendChild(el('span', null, 'Cerré una terminal vieja de ' + m + ' que estaba quieta, para que tu mensaje saliera. La conversación sigue igual.'));
  w.appendChild(amiBotonChico('Volver a abrirla', function (b) { amiArreglar(a, 'deshacer', b); }));
  return w;
}
/* un arreglo sin tarjeta de error (ya se arregló: «¡Listo!») */
function piezaArreglo(a, ar) {
  if (ar.paso !== 'listo') return null;
  var m = motorN(ar.motor), c = el('div', 'ami ok'), mo = el('div', 'mono'); mo.appendChild(monitoDe('ami', a, 44)); c.appendChild(mo);
  var t = el('div', 'tx'); t.appendChild(el('b', 't', '¡Listo!'));
  t.appendChild(el('p', null, ar.tipo === 'confianza' ? m + ' ya confía en los avisos de Workspace: desde ahora ves aquí lo que hace en la terminal.'
    : ar.tipo === 'login' ? 'Ya entraste a tu cuenta de ' + m + '. Sigo con tu mensaje.' : m + (ar.tipo === 'instalar' ? ' ya está instalado.' : ' ya está al día.') + ' Sigo con tu mensaje.'));
  c.appendChild(t); return c;
}
/* ---------- Codex: confiar UNA vez en sus hooks (D6-a) ----------
   Sin esa confianza, Codex no corre los avisos (hooks) de Workspace en su terminal: la página no ve lo que hace ahí y
   lo prohibido no se frena antes de cada herramienta. Se da en su /hooks: Workspace abre Codex («Ir a la terminal»),
   la guía va con dibujos y la página se da cuenta sola cuando quedó (se lo pregunta a Codex: hooks/list). Nada se
   teclea en Codex ni se escribe en su config. `c`: la `confianza` de la foto ({estado, total, confiados, faltan}). */
var AMI_CONF_TXT = {
  falta: { t: '{m} necesita tu permiso, una sola vez', p: 'Para que veas aquí lo que {m} hace en la terminal, y para frenar lo que no se puede hacer, {m} pide que confíes una vez en los avisos de Workspace. Te lo abro y te guío: es un minuto.' },
  modificados: { t: '{m} pide tu permiso otra vez', p: 'Los avisos de Workspace cambiaron (pasa a veces al actualizarse) y {m} pide que los confirmes de nuevo. Es lo mismo de la otra vez: un minuto.' }
};
var AMI_CONF_GUIA = [
  ['ventana', 'Abrí {m} en la terminal, en la pestaña que te digo abajo. Si te pregunta si confías en la carpeta de tu agente, di que sí.'],
  ['escribe', ['Escribe ', { k: '/hooks' }, ' y pulsa Enter.']],
  ['confia', 'Ahí están los de Workspace de este agente. Elige confiar en todos.'],
  ['listo', 'Vuelve aquí: me doy cuenta solo cuando quedó.']
];
/* sin dónde abrir la ventana: el primer paso lo haces tú, como siempre; si ya estaba abierto, vas a esa */
var AMI_CONF_ABRELO = ['ventana', 'Abre este agente en {m} desde el hub, como siempre.'];
var AMI_CONF_YA = ['ventana', '{m} ya estaba abierto en la terminal: ve a esa ventana.'];
/* B06: lo abrió (o lo encontró) y lo puso al frente en el hub */
var AMI_CONF_FRENTE = ['ventana', 'Te puse {m} al frente en la terminal. Si te pregunta si confías en la carpeta de tu agente, di que sí.'];
/* Windows: se abre en una ventana nueva de la terminal (no en el hub) */
var AMI_CONF_VENTANA = ['ventana', 'Abrí {m} en una ventana nueva de la terminal. Si te pregunta si confías en la carpeta de tu agente, di que sí.'];
/* B06: «Ahora no» se recuerda al recargar (por agente y por situación), como las demás preferencias de la página */
function confLuego(a) {
  if (L(a).confLuego) return L(a).confLuego;
  return (pagGet('luego') || {})[a.id] || '';
}
function guardarConfLuego(a, estado) {
  L(a).confLuego = estado;
  var m = Object.assign({}, pagGet('luego') || {}); m[a.id] = estado;
  pagSet('luego', m);
}
function amiConfDetalle(c) {
  var t = 'Codex no corre los hooks de un proyecto hasta que confías en ellos en su /hooks. Queda guardado en tu configuración de Codex, una vez por agente y por computadora. Sin eso, Workspace no ve lo que hace Codex en la terminal ni frena lo prohibido antes de cada herramienta.';
  if (c.total) t += '\nConfiados: ' + c.confiados + ' de ' + c.total + '.' + ((c.faltan || []).length ? ' Faltan: ' + c.faltan.join(', ') + '.' : '');
  else t += '\nCodex todavía no los cargó: se cargan al abrir este agente en Codex desde Workspace.';
  return t;
}
/* ¿va su tarjeta? Si hace falta, no hay otra tarjeta de su motor y no dijiste «Ahora no» (a esa misma situación) */
function confianzaVisible(a, f, err) {
  var c = f.confianza;
  return !!(c && c.estado !== 'listo' && !(err && err.estado) && confLuego(a) !== c.estado);
}
function tarjetaConfianza(a, c, ar) {
  var motor = 'codex', m = motorN(motor), tx = AMI_CONF_TXT[c.estado] || AMI_CONF_TXT.falta;
  if (ar && (ar.tipo !== 'confianza' || ar.motor !== motor)) ar = null;
  var paso = ar ? ar.paso : '', err = (ar && ar.error) || '', boton = null, detalle = [amiConfDetalle(c)];
  var k = el('div', 'ami'), mo = el('div', 'mono'); mo.appendChild(monitoDe('ami', a, 44)); k.appendChild(mo);
  var t = el('div', 'tx'); t.appendChild(el('b', 't', tx.t.replace(/\{m\}/g, m))); t.appendChild(el('p', null, tx.p.replace(/\{m\}/g, m)));
  if (paso === 'abriendo') t.appendChild(amiHace('Abriendo ' + m + '…', true));
  else if (paso === 'esperando') {
    var vn = !!(ar.donde && ar.donde.ventana);
    var primero = ar.abierta === 'enfocada' ? AMI_CONF_FRENTE : ar.abierta === 'ya' ? AMI_CONF_YA : vn ? AMI_CONF_VENTANA : AMI_CONF_GUIA[0];
    t.appendChild(amiGuia(motor, m, [primero].concat(AMI_CONF_GUIA.slice(1))));
    var d = dondeTerminal(ar.donde);
    t.appendChild(amiHace('Te espero' + (d ? ' (' + m + ' está en la ' + d + (vn ? '' : ' del hub') + ')' : '') + '…', true));
    /* B06: si no lo ves, lo vuelvo a abrir o a poner al frente (el mismo arreglo sigue esperando) */
    boton = amiBoton('No lo veo: llévame ahí', function (b) { amiArreglar(a, 'confiar_hooks', b); });
  } else if (paso === 'fallo' && /\.abrir_sin_herdr$/.test(err)) {
    t.appendChild(el('p', 'ojo', 'No encontré dónde abrir la ventana. Hazlo tú y sigue estos pasos; me doy cuenta solo cuando quede:'));
    t.appendChild(amiGuia(motor, m, [AMI_CONF_ABRELO].concat(AMI_CONF_GUIA.slice(1))));
    detalle.push(err);
  } else {
    if (paso === 'sin_terminar') t.appendChild(el('p', 'ojo', 'Parece que no quedó. Si en /hooks no ves los de Workspace, cierra ' + m + ' y vuelve a abrirlo desde aquí.'));
    if (paso === 'fallo') { t.appendChild(el('p', 'ojo', /\.trabajando$/.test(err) ? m + ' está contestando aquí. Cuando termine, pulsa otra vez.' : 'No pude abrir ' + m + '.')); detalle.push(err); }
    boton = amiBoton(paso ? 'Abrir ' + m + ' otra vez' : 'Abrir ' + m, function (b) { amiArreglar(a, 'confiar_hooks', b); });
  }
  var fila = el('div', 'botones'); if (boton) fila.appendChild(boton);
  fila.appendChild(amiBotonChico('Ahora no', function () {
    guardarConfLuego(a, c.estado);
    nota('Bien. ' + m + ' trabaja igual, pero aquí no verás lo que hace en su terminal ni se frenará ahí lo prohibido. Te lo vuelvo a ofrecer si cambia algo.', false);
    pintarEstadoVivo();
  }));
  t.appendChild(fila);
  var vd = amiDetalle(detalle); if (vd) t.appendChild(vd);
  k.appendChild(t);
  return k;
}
