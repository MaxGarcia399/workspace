/* ================= barra de agentes: su monito y su rayita (qué está haciendo) ================= */
var AHORA_UPD = null;
function pintarRiel() {
  var R = $('#rail');
  if (!R._lst) {                                  // armazón fijo: lista + botones de abajo (una sola vez)
    R.textContent = '';
    var l = el('div', 'lst'); R.appendChild(l); R._lst = l;
    var mas = el('button', 'rb'); mas.appendChild(icono('plus')); mas.onmouseenter = function () { tip(mas, 'Nuevo agente'); }; mas.onclick = function (e) { e.stopPropagation(); quitarTip(); crearAgente(); };
    /* abajo del riel: «+» (crear agente), «?» (la guía) y el engrane (configuración: General, Motores, Permisos, Uso, Actualizaciones) */
    var cfg = el('button', 'rb cfgb'); cfg.id = 'bCfg'; cfg.appendChild(svgEngrane()); cfg.onmouseenter = function () { tip(cfg, 'Configuración'); };
    cfg.onclick = function (e) { e.stopPropagation(); quitarTip(); configuracion(); };
    /* «?»: la guía (H5-a), encima del engrane; el mismo lugar en todas las pantallas */
    var gu = el('button', 'rb gub', '?'); gu.id = 'bGuia'; gu.onmouseenter = function () { tip(gu, 'Guía', 'Un recorrido de cinco pasos'); };
    gu.onclick = function (e) { e.stopPropagation(); quitarTip(); guia(); };
    R.appendChild(mas); R.appendChild(gu); R.appendChild(cfg);
  }
  var piezas = [];
  S.agentes.forEach(function (a, i) {
    if (i === 1) piezas.push({ k: 'sep', f: '1', quieto: true, hacer: function () { return el('div', 'sep'); } });
    var x = actividadDe(a);
    piezas.push({ k: 'ag|' + a.id, quieto: true, f: firma([a.id === S.act, a.c, a.f, a.n, a.motor, x.k, x.n, x.p].join('|')), hacer: function () { return botonAgente(a); } });
  });
  reconciliar(R._lst, piezas, 'riel');
  if (AHORA_UPD) AHORA_UPD();
}
function botonAgente(a) {
  var b = el('button', 'av7' + (a.id === S.act ? ' on' : ''));
  b.style.setProperty('--c', a.c);
  b.appendChild(monitoDe('riel', a, 48));
  b.appendChild(rayita(a));
  b.onclick = function () { elegirAgente(a.id); };
  b.onmouseenter = function () {
    tip(b, a.n, textoAct(a) + ' · ' + motorN(motorChat(a)));
    var m = monoObj('riel', a); if (!m) return;
    if (m.estado === 'duerme') { m.modoOjo = 'normal'; m.tabre = .4; setTimeout(function () { if (m.estado === 'duerme') { m.modoOjo = 'cerrado'; m.tabre = 1; } }, 900); return; }
    m.salta(.55); if (m.estado !== 'termino') { m.modoOjo = 'feliz'; setTimeout(function () { if (m.modoOjo === 'feliz' && m.estado !== 'termino') m.modoOjo = 'normal'; }, 650); }
  };
  b.oncontextmenu = function (e) { e.preventDefault(); e.stopPropagation(); quitarTip(); menuAgente(b, a); };
  return b;
}
function menuAgente(b, a) {
  pop(b, [{ t: 'Ver su resumen', run: function () { elegirAgente(a.id); abrirPanel('agente', 'Resumen'); } }]);
}
function elegirAgente(id) {
  if (!ag(id)) return;
  if (S.EDIT && S.EDIT.sucio && id !== S.act) return nota('Guarda o descarta lo que editas en ' + S.EDIT.ruta + ' antes de cambiar de agente', true);
  /* lo que escribías y adjuntabas es de ESE agente: se guarda con él y vuelve cuando regresas */
  var antes = activo();
  if (antes && antes.id !== id) { L(antes).borrador = $('#ta').value; L(antes).adj = ADJ; }
  var nuevo = ag(id);
  if (!antes || antes.id !== id) { $('#ta').value = L(nuevo).borrador || ''; ADJ = L(nuevo).adj || []; pintarAdjuntos(); }
  S.act = id; S.EDIT = null; S.RENOMBRA = '';
  pagSet('activo', id);
  var a = activo(); if (a) cargarUsoSnap(a);
  pintar(true); acelerar(4); sondeoChat();
}
function apagar() { post('/api/apagar', {}).then(function () { document.body.textContent = ''; document.body.appendChild(el('div', 'vacio', 'La página se apagó. Ábrela otra vez desde el hub.')); }, function (e) { nota(e.message, true); }); }

/* ================= arriba: el agente, sus skills y su motor ================= */
/* ¿la página le escribe a ese motor por OTRO conector suyo (Hermes y OpenClaw por su ACP)? Es un chat aparte del de
   su terminal, y el chip lo dice: «Hermes · chat aparte» (F3e) */
function chatAparte(a, mc) { var f = fotoDe(a), v = f.via; return !!(v && v.aparte && (f.motor || a.motor) === mc); }
function nombreChip(a, mc) { return motorN(mc) + (chatAparte(a, mc) ? ' · chat aparte' : ''); }
function pintarTop() {
  var a = activo(), P = $('#pill');
  if (!a) { P.textContent = ''; return; }
  var mc0 = motorChat(a), cm0 = cambioDe(a), f0 = firma([a.id, a.n, a.c, a.f, S.PANEL, mc0, !!(ejecVigente(a) || L(a).skillPend), S.motores.length, S.motores.some(function (m) { return m.id === mc0 && m.listo; }), slugChat(a), cm0 ? cm0.motor + cm0.paso : '', chatAparte(a, mc0)].join('|'));
  if (P._f === f0) { pintarUsoCaja(); pintarSend(); pintarAjustes(); return; }
  P._f = f0; P.textContent = '';
  var rs = document.documentElement.style; rs.setProperty('--ac', a.c); rs.setProperty('--acx', claroHex(a.c) ? '#151518' : '#fff');
  P.appendChild(monitoDe('pill', a, 24)); P.appendChild(el('span', null, a.n)); P.appendChild(svg('chev'));
  P.classList.toggle('on', S.PANEL === 'agente');
  P.onclick = function (e) { e.stopPropagation(); abrirPanel(S.PANEL === 'agente' ? '' : 'agente'); };
  var K = $('#bSk'); K.textContent = ''; K.appendChild(svg('skill')); K.appendChild(el('span', null, 'Skills'));
  if (ejecVigente(a) || L(a).skillPend) K.appendChild(el('i', 'd az'));
  K.classList.toggle('on', S.PANEL === 'skills');
  K.onclick = function (e) { e.stopPropagation(); abrirPanel(S.PANEL === 'skills' ? '' : 'skills'); };
  var M = $('#motor'); M.textContent = ''; var mc = motorChat(a), listo = S.motores.some(function (m) { return m.id === mc && m.listo; });
  var cm = cambioDe(a), va = cm && cm.paso !== 'listo' && cm.paso !== 'error' && cm.motor !== mc ? cm.motor : '';
  M.appendChild(el('i', 'd' + (va ? ' va' : listo || !S.motores.length ? '' : ' no'))); M.appendChild(el('span', null, (va ? motorN(mc) : nombreChip(a, mc)) + (va ? ' → ' + motorN(va) : ''))); M.appendChild(svg('chev'));
  M.title = (slugChat(a) ? 'El motor de esta conversación' : 'El motor con que empezará su conversación') +
    (!va && chatAparte(a, mc) ? ' · le escribe por su ACP: un chat aparte del de su terminal' : '');
  M.onclick = function (e) { e.stopPropagation(); menuMotor(M, a); };
  pintarUsoCaja(); pintarSend(); pintarAjustes();
}
function abrirPanel(cual, tab) {
  if (S.EDIT && S.EDIT.sucio) return nota('Guarda o descarta lo que editas en ' + S.EDIT.ruta + ' primero', true);
  S.PANEL = cual; S.EDIT = null; if (tab) S.PTAB = tab; pintarPanel(); pintarTop();
}
/* arriba se cambia el motor de ESTA conversación (sigue la misma conversación en otro motor); el de las nuevas,
   en su panel → Motor */
function menuMotor(anc, a) {
  var slug = slugChat(a), mc = motorChat(a), filas = [], oc = slug ? ocupadoDe(a) : '';
  /* solo se ofrecen los que de verdad pueden contestar: instalados Y con sesión iniciada. Ocupado: atenuados, con su
     razón, y tocar uno es «Detener y cambiar» (espera a que de verdad se detenga) */
  var usable = function (m) { return m.listo && m.sesion !== false && m.estado !== 'sin_sesion'; };
  S.motores.filter(usable).forEach(function (m) {
    var d = el('span', 'dt'); d.style.background = 'var(--ok)';
    filas.push({ marca: d, t: m.nombre, ok: m.id === mc, tenue: !!oc && m.id !== mc, sub: oc && m.id !== mc ? 'Detener y cambiar' : (tabDe(a) !== NAV && m.id !== mc ? 'en una pestaña nueva' : ''),
      run: function () { if (m.id === mc) return; if (!slug) return cambiarMotor(a, m); if (oc && fotoDe(a).estado !== 'cambiando') return detenerY(a, 'cambiar a ' + m.nombre, function () { cambiarMotorChat(a, slug, m); }, function () { cambiarMotorChat(a, slug, m, true); }); cambiarMotorChat(a, slug, m); } });
  });
  var faltan = S.motores.filter(function (m) { return !usable(m); });
  if (faltan.length) { filas.push('-'); faltan.forEach(function (m) { var d = el('span', 'dt'); d.style.background = '#55555e'; filas.push({ marca: d, t: m.nombre, sub: m.sesion === false || m.estado === 'sin_sesion' ? 'sin sesión iniciada' : (m.estado_texto || 'no está listo'), off: true }); }); }
  if (!filas.length) filas.push({ t: 'Cargando motores…', off: true });
  pop(anc, filas, oc || (tabDe(a) !== NAV ? 'Esta sesión es de su motor: otro sigue en una pestaña nueva' : slug ? 'Motor de esta conversación' : 'Motor de ' + a.n));
}
function cambiarMotorChat(a, slug, m, forzar) {
  var cm = cambioDe(a), corre = cm && cm.paso !== 'listo' && cm.paso !== 'error';
  if (m.id === motorChat(a) && !corre) return;
  /* el avance se ve en el chat, que no se borra; el chip y el uso siguen con el de antes hasta que quede listo */
  var ahora = Date.now() / 1000;
  L(a).cambio = { motor: m.id, de: corre ? cm.de : motorChat(a), paso: 'guardando', t: ahora, inicio: ahora }; L(a).paciencia = null;
  pintarEstadoVivo(); pintarCaja(); pintarTop();
  /* la misma conversación sigue con otro motor por su vía oficial (capa de control); trabajando, primero se detiene */
  post('/api/v2/motor', { agente: a.id, motor: m.id }).then(function (r) {
    /* H4-a: una sesión de su programa es de su motor: siguió en una pestaña nueva, con lo hablado y su nota */
    if (r && r.nueva && r.tab) { L(a).cambio = null; nota('Seguí con ' + m.nombre + ' en «' + r.tab.nombre + '», con lo que hablaron'); elegirTab(a, r.tab.slug, true); }
    acelerar();
  }, function (e) {
    L(a).cambio = null; pintarEstadoVivo(); pintarCaja(); pintarTop();
    if (e.status === 409 && !forzar) { pop($('#motor'), [{ t: 'Detener y cambiar', p: true, run: function () { detenerY(a, 'cambiar a ' + m.nombre, function () { cambiarMotorChat(a, slug, m, true); }); } }, { t: 'Esperar a que termine' }], e.message); return; }
    nota(e.message, true);
  });
}
/* ================= modelo y esfuerzo: diseño M-B, un botón junto a la caja de escribir =================
   La tabla de cada motor la da el servidor en su foto (pagina_v2.ajustes): SOLO lo que la capa de control sabe
   aplicar por la vía oficial de su motor; lo que no tiene, no aparece. Se aplica en su siguiente mensaje. */
var AJ_NODOS = [], AJ_VA = {};
function filasAjuste(a) { var x = fotoDe(a).ajustes || {}; return x.motor === motorChat(a) ? x.tabla || [] : []; }
function ajusteDe(a, k) {
  var x = fotoDe(a).ajustes || {}, mc = motorChat(a), val = x.motor === mc ? (x.valores || {})[k] : null;
  return { actual: (val && val.actual) || null, guardado: ((x.guardados || {})[mc] || {})[k] || null };
}
/* Codex: los niveles del modelo que tiene o que elegiste (su catálogo); los demás, todos */
function opcionesAjuste(a, f) {
  if (!f.por_modelo) return f.opciones;
  var m = ajusteDe(a, 'modelo'), v = m.guardado || (m.actual && m.actual.v), niv = v && f.por_modelo[v];
  return niv ? f.opciones.filter(function (o) { return niv.indexOf(o.v) >= 0; }) : f.opciones;
}
function textoAjuste(f, act) {
  if (!act) return null;
  var o = act.v && f.opciones.filter(function (x) { return x.v === act.v; })[0];
  return o ? o.t : act.t;
}
/* el botón junto a la caja (M-B): «Opus · medio», o «por defecto» si no elegiste */
function pintarAjustes() {
  var B = $('#aj'), a = activo(), fs = a ? filasAjuste(a) : [];
  var f0 = a ? firma(JSON.stringify([a.id, motorChat(a), fs.length, fotoDe(a).ajustes, ocupadoDe(a)])) : '';
  if (B._f === f0) return;
  B._f = f0; B.textContent = ''; B.style.display = fs.length ? '' : 'none';
  AJ_NODOS = AJ_NODOS.filter(function (n) { return n.isConnected; });
  AJ_NODOS.forEach(function (n) { n._llenar(); });
  if (!fs.length) return;
  var partes = [], tit = [];
  fs.forEach(function (f) { var t = textoAjuste(f, ajusteDe(a, f.k).actual); if (t) partes.push(t); tit.push(f.t + ': ' + (t || 'el de siempre')); });
  B.appendChild(el('span', null, partes.length ? partes.join(' · ') : 'por defecto')); B.appendChild(svg('chev'));
  B.title = 'Modelo y esfuerzo · ' + tit.join(' · ');
  B.onclick = function (e) { e.stopPropagation(); panelAjustes(B, a); };
}
function panelAjustes(anc, a) {
  cerrarCapas(); quitarTip();
  var p = el('div', 'pop ajp mB'); p.onclick = function (e) { e.stopPropagation(); };
  p.appendChild(el('div', 'h', motorN(motorChat(a)) + ' · ' + a.n)); p.appendChild(gruposAjuste(a));
  document.body.appendChild(p);
  var r = anc.getBoundingClientRect(), abajo = r.top > innerHeight / 2;   // junto a la caja: se abre hacia arriba
  if (abajo) p.style.bottom = (innerHeight - r.top + 10) + 'px'; else p.style.top = (r.bottom + 8) + 'px';
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.left - 10)) + 'px';
}
/* los botones segmentados por ajuste (en la pastilla y en el panel → Resumen → Su motor): lo actual marcado; ocupado,
   atenuados con su razón */
function gruposAjuste(a) {
  var w = el('div', 'ajg');
  w._llenar = function () {
    w.textContent = '';
    var fs = filasAjuste(a), oc = ocupadoDe(a);
    if (!fs.length) { w.appendChild(el('div', 'ajn', motorN(motorChat(a)) + ' no deja elegir aquí su modelo ni su esfuerzo por su vía oficial: usa lo de su propia configuración.')); return; }
    if (oc) w.appendChild(el('div', 'ajr', oc));
    fs.forEach(function (f) {
      var x = ajusteDe(a, f.k), act = x.actual, fila = el('div', 'ajf'), cab = el('div', 'lb');
      cab.appendChild(el('span', null, f.t)); fila.appendChild(cab);
      var lst = el('div', 'mlst');
      opcionesAjuste(a, f).forEach(function (o) {
        var b = el('button', 'mrow' + (act && act.v === o.v ? ' on' : '') + (AJ_VA[a.id + '|' + f.k] === o.v ? ' va' : ''));
        b.appendChild(el('i', 'rd')); b.appendChild(el('span', null, o.t));
        if (oc || AJ_VA[a.id + '|' + f.k]) { b.disabled = true; if (oc) b.title = oc; }
        else b.title = 'Se aplica en su siguiente mensaje';
        b.onclick = function (e) { e.stopPropagation(); if (act && act.v === o.v) return; elegirAjuste(a, f, o); };
        lst.appendChild(b);
      });
      fila.appendChild(lst); w.appendChild(fila);
    });
  };
  w._llenar(); AJ_NODOS.push(w);
  return w;
}
function elegirAjuste(a, f, o) {
  var k = a.id + '|' + f.k; AJ_VA[k] = o.v; refrescarAjustes();
  post('/api/v2/ajuste', { agente: a.id, ajuste: f.k, valor: o.v }).then(function () {
    delete AJ_VA[k];
    var x = fotoDe(a).ajustes = fotoDe(a).ajustes || {};
    (x.valores = x.valores || {})[f.k] = { actual: { v: o.v, t: o.t } };
    nota(a.n + ' usa ' + o.t + ' desde su siguiente mensaje');
    refrescarAjustes(); acelerar();
  }, function (e) { delete AJ_VA[k]; refrescarAjustes(); nota(e.message, true); });
}
function refrescarAjustes() { var B = $('#aj'); if (B) B._f = null; pintarAjustes(); }
function cambiarMotor(a, m) {
  if (m.id === a.motor) return;
  post('/api/sistema/agente/motor', { agente: a.id, motor: m.id }).then(function () {
    a.motor = m.id; nota(a.n + ' usará ' + m.nombre + ' en sus conversaciones nuevas'); cargarUsoSnap(a); pintar(true);
  }, function (e) { nota(e.message, true); });
}
/* lo que lleva gastado su motor, al lado de la caja: la métrica que más aprieta */
function pintarUsoCaja() {
  var U = $('#uso'), a = activo(), partes = [];
  if (a) {
    var foto = S.pant[a.id];
    var u = foto && Object.prototype.hasOwnProperty.call(foto, 'uso') ? (foto.uso || {}) :
        (S.usoSnap[a.id] || {}).uso || {};
    if (u.contexto != null) partes.push('Contexto ' + u.contexto + '%');
    if (u.ventana) {
      var v = u.ventana, duracion = v.minutos == null ? 'Ventana' :
          (v.minutos % 60 ? v.minutos + ' min' : (v.minutos / 60) + ' h');
      var ventana = duracion + ': ' + v.libre + '% libre';
      if (v.reinicia != null) ventana += ' · reinicia ' + new Date(v.reinicia * 1000).toLocaleString();
      partes.push(ventana);
    } else {
      partes.push(motorN(motorChat(a)) + ' no informa su límite');
    }
    if (u.semana_usada != null) partes.push('Semana ' + u.semana_usada + '% usado');
    if (u.tokens_turno != null) partes.push(u.tokens_turno + ' tokens turno');
    if (u.tokens_sesion != null) partes.push(u.tokens_sesion + ' tokens sesión');
  }
  var texto = partes.join(' · ');
  if (U.textContent !== texto) U.textContent = texto;
}
function pintarSend() {
  var s = $('#send'), a = activo(), lleno = !!($('#ta').value.trim() || ADJ.some(function (x) { return x.ruta; }));
  var resp = !!(a && modoCaja(a) === 'abierta');             // skills v11: con la pregunta abierta, enviar contesta
  var f0 = lleno + '|' + resp + '|' + (a ? a.c : '');
  if (s._f === f0) return;                                  // F5: el ícono se rehacía en cada repintado
  s._f = f0; s.textContent = '';
  if (resp) { s.appendChild(icono('up')); s.style.background = a.c; s.style.color = claroHex(a.c) ? '#111' : '#fff'; s.style.opacity = '1'; s.title = 'Enviar tu respuesta'; return; }
  s.appendChild(icono('up')); s.style.background = lleno ? '#ededf0' : (a ? a.c : '#ededf0'); s.style.color = !lleno && a && !claroHex(a.c) ? '#fff' : '#111';
  s.style.opacity = lleno ? '1' : '.55'; s.title = 'Enviar';
}
