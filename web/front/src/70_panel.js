/* ================= el panel derecho: el AGENTE o sus SKILLS ================= */
/* pintarPanel vive en 60_skills.js (skills v11: el panel también lleva el proceso de una skill) */
var TABS = ['Resumen', 'Apariencia', 'Tono', 'Motor', 'Archivos'];
function panelAgente(I) {
  var a = activo();
  var pr = el('div', 'prof'); pr.appendChild(monitoDe('panel', a, 88));
  var nm = el('div', 'nombre');
  if (S.RENOMBRA === 'agente') {
    var inp = el('input'); inp.value = a.n; inp.maxLength = 40; nm.appendChild(inp); setTimeout(function () { inp.focus(); inp.select(); }, 20);
    inp.onkeydown = function (e) {
      if (e.key === 'Escape') { S.RENOMBRA = ''; pintarPanel(); }
      if (e.key !== 'Enter') return;
      var n = inp.value.trim(); S.RENOMBRA = '';
      post('/api/front/nombre', { agente: a.id, nombre: n === a.nOrig ? '' : n }).then(function () { a.n = n || a.nOrig; pintar(true); nota(n && n !== a.nOrig ? 'En esta computadora se llama ' + a.n : 'Volvió a su nombre'); }, function (er) { nota(er.message, true); pintarPanel(); });
    };
  } else { nm.appendChild(el('span', null, a.n)); var lp = el('button', 'lapiz'); lp.appendChild(icono('lapiz')); lp.title = 'Cambiar cómo lo ves llamado'; lp.onclick = function () { S.RENOMBRA = 'agente'; pintarPanel(); }; nm.appendChild(lp); }
  pr.appendChild(nm); pr.appendChild(el('div', 'sub', a.lema || '')); I.appendChild(pr);
  var sg = el('div', 'seg7'), ind = el('i', 'ind'), C = el('div', 'tabc'); sg.appendChild(ind);
  TABS.forEach(function (t) {
    var b = el('button', t === S.PTAB ? 'on' : '', t);
    b.onclick = function () { if (S.PTAB === t) return; S.PTAB = t; sg.querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); }); mover(); C.style.opacity = 0; setTimeout(function () { llenar(); C.style.opacity = 1; }, 140); };
    sg.appendChild(b);
  });
  function mover() { var b = sg.querySelector('button.on'); if (!b) return; ind.style.width = b.offsetWidth + 'px'; ind.style.transform = 'translateX(' + b.offsetLeft + 'px)'; }
  I.appendChild(sg); I.appendChild(C); ind.style.transition = 'none'; mover(); void ind.offsetWidth; ind.style.transition = '';
  function llenar() {
    C.textContent = ''; AHORA_UPD = null;
    if (S.PTAB === 'Resumen') resumenTab(C, a);
    if (S.PTAB === 'Apariencia') aparienciaTab(C, a);
    if (S.PTAB === 'Tono') tonoTab(C, a);
    if (S.PTAB === 'Motor') motorTab(C, a);
    if (S.PTAB === 'Archivos') archivosTab(C, a);
  }
  llenar();
}

/* ---------- Resumen: qué hace ahora, su motor y sus pendientes (su STATE/PENDIENTES.md) ---------- */
var DET_ACT = { cerrado: 'Su motor se cerró; ábrelo de nuevo o sigue con otro.', no_salio: 'Un mensaje tuyo no se mandó; en el chat ves qué hacer.', enviando: 'Le está llegando lo que le escribiste.', recibido: 'Ya tiene tu mensaje; está por empezar.', cambiando: 'Está cambiando de motor; la conversación sigue igual.', pensando: 'Está armando su siguiente paso.', leyendo: 'Está leyendo lo que le pasaste.', escribiendo: 'Te está escribiendo en el chat.', listo: 'Terminó lo que le pediste.', error: 'Algo falló; dejó el detalle en el chat.', dormido: 'Su conversación está cerrada; despierta cuando le escribas.', libre: 'Disponible para lo que necesites.' };
function resumenTab(C, a) {
  var ah = el('div', 'ahora'); ah.style.setProperty('--c', a.c); C.appendChild(ah);
  function upd() {
    var x = actividadDe(a), f0 = firma([x.k, x.n, x.p, x.s].join('|'));
    if (ah._f === f0) return;
    ah._f = f0; ah.textContent = ''; var a1 = el('div', 'a1'); a1.appendChild(rayita(a));
    var tt = TXT_ACT[x.k]; a1.appendChild(el('b', null, tt.charAt(0).toUpperCase() + tt.slice(1))); ah.appendChild(a1);
    var det = x.k === 'skill' ? '«' + x.s + '» · paso ' + (x.p + 1) + ' de ' + x.n : x.k === 'espera' ? 'Te espera en el chat' + (x.s ? ' para «' + x.s + '».' : '.') : DET_ACT[x.k];
    ah.appendChild(el('p', null, det));
    if (x.k === 'skill') { var pg = el('div', 'prog'); for (var j = 0; j < x.n; j++) pg.appendChild(el('i', j < x.p ? 'h' : j === x.p ? 'a' : '')); ah.appendChild(pg); }
    if (['skill', 'espera', 'listo'].indexOf(x.k) >= 0) { var ir = el('button', 'ir', 'Ver en el chat ›'); ir.onclick = function () { S.PANEL = ''; pintarPanel(); pintarTop(); }; ah.appendChild(ir); }
  }
  upd(); AHORA_UPD = function () { if (ah.isConnected) upd(); else AHORA_UPD = null; };
  var l1 = el('div', 'lbl7'); l1.appendChild(el('span', null, 'Su motor')); var cm = el('button', null, 'Cambiar ›'); cm.onclick = function () { cambiarTab('Motor'); }; l1.appendChild(cm); C.appendChild(l1);
  var mw = el('div'); C.appendChild(mw); bloqueMotor(mw, a);
  if (filasAjuste(a).length) mw.appendChild(gruposAjuste(a));      // §6: los mismos botones de la pastilla de arriba
  var l2 = el('div', 'lbl7'); l2.appendChild(el('span', null, 'Pendientes')); var ab = el('button', null, 'STATE/PENDIENTES.md ›'); ab.onclick = function () { abrirArchivo(a, 'STATE/PENDIENTES.md'); }; l2.appendChild(ab); C.appendChild(l2);
  var cual = el('div', 'cual7'), suyos = el('button', PEND_TODOS ? '' : 'on', 'Suyos'), todos = el('button', PEND_TODOS ? 'on' : '', 'De todos');
  cual.appendChild(suyos); cual.appendChild(el('span', null, '·')); cual.appendChild(todos); C.appendChild(cual);
  var pw = el('div'); C.appendChild(pw);
  function llenarPend() { if (PEND_TODOS) bloqueTodos(pw); else bloquePend(pw, a); }
  suyos.onclick = function () { PEND_TODOS = false; suyos.className = 'on'; todos.className = ''; pw._f = null; llenarPend(); };
  todos.onclick = function () { PEND_TODOS = true; todos.className = 'on'; suyos.className = ''; pw._f = null; llenarPend(); };
  llenarPend();
  /* F15: se repintan solos cuando cambian (su firma llega en la foto del agente), sin reabrir el panel */
  PEND_UPD = function () { if (pw.isConnected) llenarPend(); else PEND_UPD = null; };
  bloqueApartar(C, a);                                             // archivar · quitar de Workspace (72_apartar.js)
}
var PEND_TODOS = false, PEND_UPD = null;
/* «De todos»: los pendientes abiertos de todos los agentes, cada uno con su monito, para cruzarlos (§5) */
function bloqueTodos(C) {
  if (!C.firstChild) C.appendChild(el('div', 'pvacio', 'Leyendo los pendientes de todos…'));
  api('/api/front/pendientes/todos').then(function (d) {
    var f0 = JSON.stringify(d.agentes); if (C._f === f0) return; C._f = f0; C.textContent = '';
    var ul = el('ul', 'todos7'), hay = false;
    (d.agentes || []).forEach(function (x) {
      var a = ag(x.agente); if (!a) return;
      x.items.forEach(function (it) {
        hay = true; var li = el('li'); li.appendChild(monito(a.c, a.f, 18, { quieto: true })); li.appendChild(el('span', null, it.texto));
        li.title = a.n + (it.tipo === 'conversacion' ? ' · lo anotó en su conversación (' + it.id + ')' : '') + ' · tócalo para marcarlo hecho';
        li.onclick = function () { post('/api/front/pendiente', { agente: a.id, accion: 'marcar', id: it.id, hecho: true }).then(function () { nota('Marcado en los pendientes de ' + a.n); C._f = null; bloqueTodos(C); }, function (e) { nota(e.message, true); }); };
        ul.appendChild(li);
      });
    });
    if (!hay) ul.appendChild(el('div', 'pvacio', 'Nadie tiene pendientes abiertos.'));
    C.appendChild(ul);
  }, function (e) { C.textContent = ''; C.appendChild(el('div', 'pvacio', e.message)); });
}
function cambiarTab(t) { S.PTAB = t; pintarPanel(); }
var TIPO_TXT = { sub: 'suscripción', cuota: 'plan con cuota', api: 'API', local: 'local', nada: 'sin datos' };
function bloqueMotor(C, a) {
  var x = usoDe(a), u = x.u, w = el('div', 'mot'), m1 = el('div', 'm1'), tx = el('div', 'tx'); w.appendChild(m1);
  var nom = el('b', null, motorN(motorChat(a))); nom.appendChild(el('span', 'tipo', TIPO_TXT[x.tipo])); tx.appendChild(nom);
  function barra(pc, izq, der) { var br = el('div', 'ubar'), bi = el('i', pc >= 80 ? 'al' : ''); bi.style.width = Math.round(pc) + '%'; br.appendChild(bi); w.appendChild(br); var pe = el('div', 'pie2'); pe.appendChild(el('span', null, izq)); pe.appendChild(el('span', null, der)); w.appendChild(pe); }
  if (x.tipo === 'sub' && u.sesion == null && u.semana == null) {
    m1.appendChild(tx); tx.appendChild(el('small', null, 'De tu plan. El porcentaje aparece en cuanto le escribas.'));
  } else if (x.tipo === 'sub') {
    var ses = pctNum(u.sesion), sem = pctNum(u.semana), prin = ses != null ? ses : sem;
    m1.appendChild(anillo(58, (prin || 0) / 100, Math.round(prin || 0) + '%', prin >= 80 ? '#e7a43a' : '#e6e6eb'));
    tx.appendChild(el('small', null, ses != null ? 'de tu ventana de 5 h' : 'de tu semana'));
    if (u.reinicia) tx.appendChild(el('small', null, 'se renueva en ' + u.reinicia));
    if (x.edad) tx.appendChild(el('small', null, 'actualizado ' + cuando(Date.now() - x.edad * 1000)));
    if (u.gasto) tx.appendChild(el('small', null, u.gasto + ' en esta sesión'));
    m1.appendChild(tx);
    if (ses != null && sem != null) barra(sem, 'Esta semana', Math.round(sem) + '%');
  } else if (x.tipo === 'cuota') {
    m1.appendChild(tx); tx.appendChild(el('small', null, u.creditos)); if (u.reinicia) tx.appendChild(el('small', null, 'se renueva en ' + u.reinicia));
  } else if (x.tipo === 'api') {
    var g = el('div', 'big', u.gasto); m1.appendChild(g); m1.appendChild(tx); tx.appendChild(el('small', null, 'gastado en esta sesión'));
    if (u.contexto != null) barra(pctNum(u.contexto), 'Contexto', Math.round(pctNum(u.contexto)) + '%');
  } else if (x.tipo === 'local') {
    m1.appendChild(el('div', 'big', 'Gratis')); m1.appendChild(tx); tx.appendChild(el('small', null, 'corre en esta computadora'));
  } else {
    m1.appendChild(tx); tx.appendChild(el('small', null, chatAbierto(a) ? 'Su motor no enseña cuánto llevas usado.' : 'Se ve cuando su conversación está abierta.'));
    if (u.contexto != null) barra(pctNum(u.contexto), 'Contexto', Math.round(pctNum(u.contexto)) + '%');
  }
  C.textContent = ''; C.appendChild(w);
}
/* sus pendientes de verdad (STATE/PENDIENTES.md). Si su cerebro se ordena por inbox, el cambio va a su inbox y
   se ve aquí como «por aplicar» hasta que su memoria lo consolide; si no, se escribe directo (con respaldo). */
var PEND_CACHE = {};
function bloquePend(C, a) {
  if (PEND_CACHE[a.id]) pintarPend(C, a, PEND_CACHE[a.id]);          // lo último que se leyó, al instante (sin «Leyendo…»)
  else if (!C.firstChild) C.appendChild(el('div', 'pvacio', 'Leyendo sus pendientes…'));
  api('/api/front/pendientes?agente=' + encodeURIComponent(a.id)).then(function (d) { var f0 = JSON.stringify(d.items) + d.modo; if (C._f !== f0 && C.isConnected) { C._f = f0; pintarPend(C, a, d); } PEND_CACHE[a.id] = d; },
    function (e) { C.textContent = ''; C.appendChild(el('div', 'pvacio', e.status === 404 ? 'Este agente no tiene cerebro en esta computadora.' : e.message)); });
}
function pintarPend(C, a, d) {
  C.textContent = '';
  var items = d.items.filter(function (x) { return !x.pausa; }), col = a.c === '#ffffff' ? '#e6e6eb' : a.c, w = el('div', 'pen'); w.style.setProperty('--c', col);
  var hechos = items.filter(function (x) { return x.hecho; }).length;
  w.appendChild(anillo(50, items.length ? hechos / items.length : 0, hechos + '/' + items.length, col));
  var ul = el('ul');
  if (!items.length) ul.appendChild(el('div', 'pvacio', d.existe ? 'No tiene pendientes abiertos.' : 'Todavía no tiene archivo de pendientes; el primero que agregues lo crea.'));
  var orden = items.filter(function (x) { return !x.hecho; }).concat(items.filter(function (x) { return x.hecho; }).slice(-3));
  function enviar(cuerpo, aviso, alFallar) {
    post('/api/front/pendiente', Object.assign({ agente: a.id }, cuerpo)).then(function (r) { nota(r.inbox ? 'Lo dejé en su inbox; su memoria lo aplica al consolidar' : aviso); PEND_CACHE[a.id] = r; C._f = JSON.stringify(r.items) + r.modo; pintarPend(C, a, r); },
      function (e) { nota(e.message, true); bloquePend(C, a); if (alFallar) alFallar(); });
  }
  orden.slice(0, 6).forEach(function (it) {
    var li = el('li', it.hecho ? 'h' : ''); li.appendChild(el('i'));
    var tx = el('span', null, it.texto); li.appendChild(tx);
    var extra = [it.quien, it.fecha].filter(Boolean).join(' · ');
    li.title = (extra ? extra + '\n' : '') + (it.por_aplicar ? 'Por aplicar: está en su inbox.' : '') + (it.tipo === 'conversacion' ? 'Lo anotó en su conversación (' + it.id + ').' : '');
    if (it.tipo === 'conversacion') li.classList.add('conv');
    if (it.por_aplicar) li.style.opacity = '.7';
    li.onclick = function () { li.classList.toggle('h'); enviar({ accion: 'marcar', id: it.id, hecho: !it.hecho }, 'Guardado en su STATE/PENDIENTES.md'); };
    ul.appendChild(li);
  });
  var abiertos = items.filter(function (x) { return !x.hecho; }).length;
  if (abiertos > 6) { var mas = el('button', 'mas', 'y ' + (abiertos - 6) + ' más ›'); mas.onclick = function () { abrirArchivo(a, 'STATE/PENDIENTES.md'); }; ul.appendChild(mas); }
  var ad = el('input', 'addp'); ad.placeholder = '+ Agregar pendiente'; ad.maxLength = 300;
  ad.onkeydown = function (e) {
    if (e.key !== 'Enter' || !ad.value.trim()) return;
    var t = ad.value.trim(); ad.value = ''; ad.disabled = true;
    enviar({ accion: 'agregar', texto: t }, 'Agregado a su STATE/PENDIENTES.md', function () { setTimeout(function () { var n = C.querySelector('.addp'); if (n) { n.value = t; n.focus(); } }, 300); });
  };
  ul.appendChild(ad); w.appendChild(ul); C.appendChild(w);
  if (d.modo === 'inbox') C.appendChild(el('div', 'pvacio', 'Su memoria ordena este archivo: lo que cambies aquí va a su inbox.')).style.marginTop = '6px';
}

/* ---------- Apariencia ---------- */
function aparienciaTab(C, a) {
  var fs = el('div', 'formas6');
  FORMAS.forEach(function (f) { var b = el('button', f === a.f ? 'on' : ''); b.title = NOMBRES_FORMA[f]; b.appendChild(monito(a.c, f, 32, { quieto: true })); b.onclick = function () { guardarApariencia(a, { forma: f }); }; fs.appendChild(b); });
  C.appendChild(fs);
  var cs = el('div', 'cols6');
  COLORES.forEach(function (c) { var b = el('button', c === a.c ? 'on' : ''); b.style.background = c; b.onclick = function () { guardarApariencia(a, { color: c }); }; cs.appendChild(b); });
  C.appendChild(cs);
  C.appendChild(el('div', 'pvacio', 'Se guarda en esta computadora.')).style.marginTop = '14px';
}
function guardarApariencia(a, cambio) {
  var antes = { f: a.f, c: a.c }; if (cambio.forma) a.f = cambio.forma; if (cambio.color) a.c = cambio.color; pintar(true);
  post('/api/front/apariencia', Object.assign({ agente: a.id }, cambio)).catch(function (e) { a.f = antes.f; a.c = antes.c; pintar(true); nota(e.message, true); });
}

/* ---------- Tono: estilos hechos, cada uno con su ejemplo y la instrucción que de verdad recibe ---------- */
var TONO = {}, FINO = false;
function tonoTab(C, a) {
  C.appendChild(el('div', 'pvacio', 'Cargando sus estilos…'));
  api('/api/front/tono?agente=' + encodeURIComponent(a.id)).then(function (d) { TONO[a.id] = d; C.textContent = ''; tonoPintar(C, a, d); }, function (e) { C.textContent = ''; C.appendChild(el('div', 'pvacio', e.message)); });
}
function huella(v, diales) { var h = el('span', 'hue'); v.forEach(function (x, i) { var b = el('i'); b.style.height = (3 + x * 3) + 'px'; h.appendChild(b); }); h.title = diales.map(function (d, i) { return d.label + ' ' + v[i] + '/5'; }).join('\n'); return h; }
function tonoPintar(C, a, d) {
  var tarjetas = [], grupo = '';
  d.estilos.forEach(function (p) {
    if (p.grupo !== grupo) { grupo = p.grupo; C.appendChild(el('div', 'lbl7', grupo)); }
    var w = el('div', 'est'), b = el('button'); b.appendChild(el('i', 'rd'));
    var t = el('div', 'tt'); t.appendChild(el('b', null, p.nombre)); t.appendChild(el('small', null, p.desc)); b.appendChild(t); b.appendChild(huella(p.huella, d.diales)); w.appendChild(b);
    var cu = el('div', 'cu'), d1 = el('div'), d2 = el('div'); cu.appendChild(d1); d1.appendChild(d2);
    d2.appendChild(el('div', 'mq', d.pregunta));
    var mr = el('div', 'mr'), slot = el('span'); mr.appendChild(slot); mr.appendChild(el('div', 'mt', p.ejemplo)); d2.appendChild(mr);
    var vi = el('button', 'verins', 'Ver la instrucción que recibe ›'), ins = el('div', 'ins', p.instruccion || 'Ninguna: todo en neutro.'); ins.style.display = 'none';
    vi.onclick = function () { var on = ins.style.display === 'none'; ins.style.display = on ? '' : 'none'; vi.textContent = on ? 'Ocultar la instrucción' : 'Ver la instrucción que recibe ›'; };
    d2.appendChild(vi); d2.appendChild(ins); w.appendChild(cu); C.appendChild(w);
    tarjetas.push([p.nombre, w, slot]);
    b.onclick = function () { guardarTono(a, p.niveles, function (r) { d.niveles = r.niveles; d.estilo = r.estilo; marcar(); fu(); }); };
  });
  function marcar() { tarjetas.forEach(function (x) { var on = x[0] === d.estilo; x[1].classList.toggle('on', on); if (on) x[2].appendChild(monitoDe('tono', a, 20)); }); }
  var fb = el('button', 'fino' + (FINO ? ' on' : '')), fl = el('span', 'fl'); fl.appendChild(icono('der'));
  var fs2 = el('small'); fb.appendChild(fl); fb.appendChild(el('span', null, '¿Ninguno te queda? Ajústalo a mano')); fb.appendChild(fs2); C.appendChild(fb);
  var fc = el('div', 'finoc' + (FINO ? ' on' : '')), fi = el('div'); fi.style.paddingTop = '8px'; fc.appendChild(fi); C.appendChild(fc);
  fb.onclick = function () { FINO = !FINO; fb.classList.toggle('on', FINO); fc.classList.toggle('on', FINO); };
  var filas = [];
  d.diales.forEach(function (dl) {
    var r = el('div', 'f3'); r.appendChild(el('span', null, dl.label)); var sg = el('div', 's3'); r.appendChild(sg);
    [[dl.eje[0], 1], ['normal', 3], [dl.eje[1], 5]].forEach(function (op) {
      var bt = el('button', null, op[0]); bt.onclick = function () { var nv = {}; nv[dl.key] = op[1]; guardarTono(a, nv, function (res) { d.niveles = res.niveles; d.estilo = res.estilo; marcar(); fu(); }); }; sg.appendChild(bt);
    });
    filas.push(function () { var v = d.niveles[dl.key] || 3, k = v <= 2 ? 0 : v === 3 ? 1 : 2; sg.querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('on', i === k); }); });
    fi.appendChild(r);
  });
  function fu() { filas.forEach(function (f) { f(); }); fs2.textContent = d.estilo ? '' : '· a tu gusto'; }
  marcar(); fu();
}
function guardarTono(a, niveles, listo) {
  post('/api/front/tono', { agente: a.id, niveles: niveles }).then(function (r) { listo(r); nota('Tono guardado: se nota desde su siguiente mensaje'); }, function (e) { nota(e.message, true); });
}

/* ---------- Motor ---------- */
function motorTab(C, a) {
  var lm = el('div', 'lista7'); C.appendChild(lm);
  if (!S.motores.length) { lm.appendChild(el('div', 'pvacio', 'Cargando motores…')); cargarMotores().then(function () { if (lm.isConnected) { C.textContent = ''; motorTab(C, a); } }); return; }
  S.motores.forEach(function (m) {
    var b = el('button', 'opc' + (m.id === a.motor ? ' on' : '') + (m.listo ? '' : ' no')); b.appendChild(el('i', 'rd'));
    var t = el('div'); t.appendChild(el('b', null, m.nombre)); t.appendChild(el('small', null, m.listo ? (m.agentes && m.agentes.length ? 'lo usan ' + m.agentes.length + (m.agentes.length === 1 ? ' agente' : ' agentes') : 'listo') : (m.estado_texto || 'no está listo'))); b.appendChild(t);
    if (!m.listo) b.disabled = true;
    b.onclick = function () { cambiarMotor(a, m); lm.querySelectorAll('.opc').forEach(function (x) { x.classList.toggle('on', x === b); }); };
    lm.appendChild(b);
  });
  C.appendChild(el('div', 'pvacio', 'Es el motor de sus conversaciones nuevas. El de la conversación de ahora se cambia arriba, junto a Skills. Cómo está cada uno: Configuración → Motores.')).style.marginTop = '12px';
}

/* ---------- Archivos ---------- */
function archivosTab(C, a) {
  C.appendChild(el('div', 'pvacio', 'Leyendo su cerebro…'));
  api('/api/front/archivos?agente=' + encodeURIComponent(a.id)).then(function (d) {
    C.textContent = '';
    if (!d.tiene_cerebro) return C.appendChild(el('div', 'pvacio', 'Este agente no tiene cerebro en esta computadora.'));
    d.archivos.forEach(function (f) {
      var b = el('button', 'ar7' + (f.existe ? '' : ' falta')); b.appendChild(el('i', 'di'));
      var t = el('div', 't'); t.appendChild(el('b', null, f.nombre + (f.editable ? '' : ' · solo lectura'))); t.appendChild(el('small', null, f.ruta + (f.existe ? '' : ' · no existe'))); b.appendChild(t); b.appendChild(chevDer());
      b.onclick = function () { abrirArchivo(a, f.ruta); };
      C.appendChild(b);
    });
  }, function (e) { C.textContent = ''; C.appendChild(el('div', 'pvacio', e.message)); });
}
function abrirArchivo(a, ruta) {
  if (S.EDIT && S.EDIT.sucio) return nota('Guarda o descarta lo que editas en ' + S.EDIT.ruta + ' primero', true);
  api('/api/front/archivo?agente=' + encodeURIComponent(a.id) + '&ruta=' + encodeURIComponent(ruta)).then(function (f) {
    if (S.act !== a.id) return;
    f.agente = a.id; S.EDIT = f; S.PANEL = 'agente'; pintarPanel(); pintarTop();
  }, function (e) { nota(e.message, true); });
}
function descartarEdicion(ancla, luego) {
  if (!S.EDIT || !S.EDIT.sucio) { S.EDIT = null; return luego(); }
  pop(ancla, [{ t: 'Descartar lo que cambiaste', rojo: true, run: function () { S.EDIT = null; luego(); } }, { t: 'Seguir editando' }], '¿Salir sin guardar?');
}
function editor(I) {
  var f = S.EDIT, a = ag(f.agente) || activo(), d = el('div', 'ed');
  var eh = el('div', 'eh'), back = el('button', 'bt sm', '‹ ' + a.n); back.onclick = function (e) { e.stopPropagation(); descartarEdicion(back, function () { pintarPanel(); }); }; eh.appendChild(back);
  var t = el('div'); t.appendChild(el('b', null, f.nombre)); t.appendChild(el('br')); t.appendChild(el('small', null, f.ruta)); eh.appendChild(t); d.appendChild(eh);
  var ta = el('textarea'); ta.value = f.borrador != null ? f.borrador : f.texto; ta.spellcheck = false; ta.readOnly = !f.editable; d.appendChild(ta);
  ta.oninput = function () { f.borrador = ta.value; f.sucio = ta.value !== f.texto; };
  var ef = el('div', 'ef'); ef.appendChild(el('small', null, f.editable ? 'Antes de guardar se respalda lo de antes (fuera del cerebro); puedes deshacer.' : 'Lo ordena su memoria: aquí solo se lee.'));
  var can = el('button', 'bt sm', f.editable ? 'Cancelar' : 'Cerrar'); can.onclick = function (e) { e.stopPropagation(); descartarEdicion(can, function () { pintarPanel(); }); }; ef.appendChild(can);
  if (f.editable) {
    var ok = el('button', 'bt sm p', 'Guardar');
    ok.onclick = function () {
      var antes = f.texto, nuevo = ta.value; ok.disabled = true;
      post('/api/front/archivo', { agente: f.agente, ruta: f.ruta, texto: nuevo, firma: f.firma }).then(function (r) {
        S.EDIT = null; pintarPanel();
        var n = el('div', 'nota', 'Guardado en ' + f.ruta + ' · '), u = el('button', null, 'Deshacer'); u.style.textDecoration = 'underline';
        u.onclick = function () { n.remove(); post('/api/front/archivo', { agente: f.agente, ruta: f.ruta, texto: antes, firma: r.firma }).then(function () { nota('Deshecho'); pintarPanel(); }, function (e) { nota(e.message, true); }); };
        n.appendChild(u); document.body.appendChild(n); setTimeout(function () { n.remove(); }, 6000);
      }, function (e) { ok.disabled = false; nota(e.message, true); });
    };
    ef.appendChild(ok);
  }
  d.appendChild(ef); I.appendChild(d);
  if (f.editable && f.sucio) setTimeout(function () { ta.focus(); }, 0);
}
