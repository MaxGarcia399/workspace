/* ================= E1 · entregas en la burbuja =================
   Parte de la burbuja (la arma WSM.montar, con sus mismas zonas de clic y su mismo motor de movimiento). El ajuste del
   dueño (22-nov): el monito es la superficie principal; lo largo pasa callado en segundo plano y el monito solo llama
   la atención cuando termina o te necesita (un toque suave: brinca, sale un globito y un número; nunca toma el teclado
   ni suena). Lo demás, solo si lo pides.
     · La tarjeta de cada entrega: miniatura de verdad (la hace la app), [Abrir] [Vista rápida] [Mandar a…] [⋯],
       «Arrástralo…» (el arrastre lo arranca la app) y «Pedir cambios» (la v2 sale en la MISMA tarjeta).
     · La tarjeta de encargo: la arma la app (lo que pediste, el archivo de verdad, la plantilla, lo que puede y dónde
       queda); aquí solo se pinta, con [Encargar] [Mejor aquí, corto] [No]. Con «Encargar» se vuelve su avance.
     · El toque: el nido brinca, un globito «<agente> terminó · archivo» [Ver] y un número en el nido.
     · El chat grande (⤢): el mismo chat en grande, con tus agentes a un lado y «Te esperan» y «Entregas» al otro
       (ronda 2, bloque G). Solo cuando lo abres; no se cierra solo.
     · Los botones de la barra según lo que tienes enfrente (texto seleccionado, un archivo, una página, nada).
   Todo sale por el `host` de la burbuja (la app o el puente): nada se abre desde aquí.
   Movimiento: cada pieza tiene UN dueño de su animación (su clase: entra/sale); lo que cambia de alto lo desliza
   `acomodar` de la burbuja; lo que ya se ve no se vuelve a animar; con «reducir movimiento», nada se mueve. */
var WSMEntregas = (function () {
  var R = {}, M = { alHost: null };
  var S = {
    cartas: {},          // agente|ruta (la que pidió la tarjeta) → {n, agente, ruta, info, img, menu, abierta}
    encargos: {},        // agente → [encargos de su foto]
    vistos: {},          // id de encargo → su último estado (para saber cuándo cambió)
    cargado: {},         // agente → ya llegó su primera lista (lo de antes no te toca)
    nodos: {},           // id de propuesta o encargo → su tarjeta en la burbuja
    propuestas: {},      // id → datos de la app
    refs: {},            // ref (propuesta o «pedir cambios») → id del encargo
    siguiendo: [],       // ids (propuesta o encargo) que se ven en la burbuja del elegido
    botones: null, plantillas: [], frente: { tipo: 'nada' }, menuBarra: '', pendiente: null,
    grande: { abierto: false, listo: false, col: false }, historial: {}, lista: {},
    toque: null, esperan: {}, zonasK: ''
  };
  var ESTADO_TXT = { en_cola: 'en fila · empieza en cuanto pueda', trabajando: 'trabajando en segundo plano',
    necesita: 'te necesita', listo: 'terminó', error: 'no pudo terminar', parado: 'lo paraste', interrumpido: 'se interrumpió' };
  /* lo que pasó con tu clic, en una línea (lo dice la app o el puente con WSMEntregas.hecho) */
  var HECHO_TXT = {
    abierto: 'Listo, lo abrí.', revelado: 'Te lo enseñé en Finder.', vista: 'Vista rápida abierta (Esc la cierra).',
    copiado: 'Copiado ✓ Pégalo donde quieras.', copiado_texto: 'Copié su respuesta ✓', compartir: 'Elige con qué compartirlo.',
    correo: 'Te abrí un correo nuevo con el archivo. Tú lo envías.', guardado: 'Guardé una copia ✓',
    soltado: 'Listo: lo soltaste en la otra app.'
  };
  var NO_TXT = {
    abierto: 'No pude abrir ese archivo: ya no está en su carpeta, o se movió.', revelado: 'No pude enseñarlo en Finder: ya no está en su carpeta, o se movió.',
    no_abierto: 'No pude abrir ese archivo: ya no está en su carpeta, o se movió.',
    vista: 'No pude enseñarlo en Vista rápida. Prueba con «Abrir».', copiado: 'No pude copiarlo. Prueba otra vez.',
    copiado_texto: 'No pude copiar su respuesta. Prueba otra vez.', compartir: 'No pude abrir el menú de compartir. Prueba con «Copiar el archivo».',
    correo: 'No encontré una app de correo lista en tu Mac. Usa «Copiar el archivo» y pégalo en tu correo.',
    guardado: 'No pude guardar la copia. Prueba en otra carpeta.', no_guardado: 'No pude guardar la copia. Prueba en otra carpeta.',
    sin_ruta: 'Todavía estoy preparando ese archivo. Inténtalo otra vez en un segundo.',
    sin_archivo: 'No encuentro el archivo de verdad detrás de esa ventana. Suéltalo en mí.',
    sin_respuesta: 'Mi app no respondió a ese botón. Ciérrame y vuelve a abrirme.'
  };
  /* los clics que esperan respuesta de la app (si no llega, se dice: nada de botones que no hacen nada) */
  var ESPERA_HECHO_MS = 4500;
  var CAMBIOS = ['Más corto', 'En inglés'];
  var COLOR_EXT = { pptx: '#e0613a', ppt: '#e0613a', key: '#3a8ee0', docx: '#3a72e0', doc: '#3a72e0', pages: '#e08a3a',
    xlsx: '#2f9e5a', xls: '#2f9e5a', csv: '#2f9e5a', numbers: '#2f9e5a', pdf: '#d64545', md: '#8a8a96', txt: '#8a8a96' };

  function host(op) {
    if (M.alHost) { try { M.alHost(op); } catch (e) { } return; }
    try { WSM.host(op); } catch (e) { }
  }
  function nodo(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
  function boton(c, txt, fn) { var b = nodo('button', c, txt); b.onclick = function (ev) { if (ev && ev.stopPropagation) ev.stopPropagation(); fn(b); }; return b; }
  function acomodar(fn) { try { WSM.acomodar(fn); } catch (e) { fn(); } }
  function quitar(n, ms, fn) { try { WSM.salir(n, ms, fn); } catch (e) { fn(); } }
  function entra(n) { try { if (n && n.animate && !WSM.quieto() && typeof n.offsetHeight === 'number') { n.classList.remove('entra'); void n.offsetWidth; n.classList.add('entra'); } } catch (e) { } }
  /* la imagen de una miniatura, encima de sí misma, desvaneciéndose (la nueva aparece debajo: sin brinco) */
  function cruzar(mini) {
    try {
      var im = null; [].slice.call(mini.children || []).forEach(function (x) { if (x.tagName === 'IMG' && !im) im = x; });
      if (!im || !im.animate || WSM.quieto()) return;
      var g = im.cloneNode(true); g.className = 'wsm-cruce'; mini.appendChild(g);
      var a = g.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, easing: 'ease-out', fill: 'forwards' });
      a.onfinish = function () { g.remove(); };
    } catch (e) { }
  }
  function fantasma(n) { try { if (n && n.animate && !WSM.quieto() && n.cloneNode && n.parentNode) { var g = n.cloneNode(true); g.classList.remove('entra'); g.classList.add('wsm-fantasma'); g.style.left = n.offsetLeft + 'px'; g.style.top = n.offsetTop + 'px'; g.style.width = n.offsetWidth + 'px'; n.parentNode.appendChild(g); var a = g.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 160, fill: 'forwards' }); a.onfinish = function () { g.remove(); }; } } catch (e) { } }
  function s() { return WSM.s; }
  function ag(id) { var l = (s() && s().agentes) || []; for (var i = 0; i < l.length; i++) if (l[i].id === id) return l[i]; return null; }
  function nombre(id) { var a = ag(id); return a ? a.n : id; }
  function enApp() { return document.documentElement.classList.contains('wsm-app'); }
  function clave(a, r) { return a + '|' + r; }
  function ext(r) { var m = /\.([A-Za-z0-9]{1,8})$/.exec(String(r || '')); return m ? m[1].toLowerCase() : ''; }
  function base(r) { return String(r || '').split(/[\\/]/).pop() || r; }
  function tam(b) { b = +b || 0; return b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : b >= 1024 ? Math.round(b / 1024) + ' KB' : b ? b + ' B' : ''; }
  function hace(t) {
    var d = Math.max(0, Date.now() / 1000 - (+t || 0));
    return d < 60 ? 'ahora' : d < 3600 ? 'hace ' + Math.round(d / 60) + ' min' : d < 86400 ? 'hace ' + Math.round(d / 3600) + ' h' : 'hace ' + Math.round(d / 86400) + ' d';
  }
  function rect(n) { try { var r = n.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; } catch (e) { return [0, 0, 0, 0]; } }

  /* ---------- montar: su caja en la burbuja, el número del nido y el globito ---------- */
  function montar(r) {
    R.w = r;
    R.encs = nodo('div', 'wsm-encs'); R.encs.hidden = true;
    if (r.globo && r.sigue && r.sigue.parentNode === r.globo && r.globo.insertBefore) r.globo.insertBefore(R.encs, r.sigue); else if (r.globo) r.globo.appendChild(R.encs);
    R.ver = boton('wsm-x wsm-gr', '⤢', function () { abrirGrande(); }); R.ver.title = 'Grande: el mismo chat en una ventana grande';
    if (r.globo) r.globo.appendChild(R.ver);
    R.botones = nodo('div', 'wsm-botones'); R.botones.hidden = true;
    R.menuB = nodo('div', 'wsm-menub'); R.menuB.hidden = true;
    var caja = null; [].slice.call((r.barra && r.barra.children) || []).forEach(function (c) { if (/wsm-caja/.test(c.className)) caja = c; });
    if (caja && r.barra.insertBefore) { r.barra.insertBefore(R.botones, caja); r.barra.insertBefore(R.menuB, caja); }
    else if (r.barra) { r.barra.appendChild(R.botones); r.barra.appendChild(R.menuB); }
    R.insignia = nodo('b', 'wsm-insignia'); R.insignia.hidden = true;
    if (r.nido) r.nido.appendChild(R.insignia);
    R.toque = nodo('div', 'wsm-toque'); R.toque.hidden = true;
    if (r.raiz) r.raiz.appendChild(R.toque);
    R.grande = nodo('div', 'wsm-grande'); R.grande.hidden = true;
    if (r.raiz && r.raiz.insertBefore && r.globo) r.raiz.insertBefore(R.grande, r.globo); else if (r.raiz) r.raiz.appendChild(R.grande);
    return W;
  }
  function piezas() { return [R.toque, R.grande].filter(function (n) { return n && !n.hidden; }); }
  /* su caja de tarjetas en la burbuja (la burbuja la pone dentro de su plática) */
  function piezasDentro() { return R.encs || null; }

  /* ---------- lo que llega (del puente o de la app) ---------- */
  function recibir(ev) {
    var t = ev && ev.t;
    if (t === 'entrega') { alEntrega(ev); return true; }
    if (t === 'encargos') { alEncargos(ev.agente, ev.lista || []); return true; }
    if (t === 'encargo') { alEncargo(ev); return true; }
    if (t === 'pasado') { alPasado(ev); return true; }
    if (t === 'botones') { S.botones = ev.botones || null; S.plantillas = ev.plantillas || []; pintarBotones(); return true; }
    if (t === 'historial') { S.historial[ev.agente] = ev.turnos || []; return true; }
    if (t === 'entregas') { S.lista[ev.agente] = ev.lista || []; pedirTodas(ev.agente, ev.lista || []); if (S.grande.abierto) pintarGrande(); return true; }
    return false;
  }

  /* ---------- la tarjeta de una entrega ---------- */
  function tarjeta(x, agente) {
    var k = clave(agente, x.ruta), c = S.cartas[k];
    if (c) return c.n;
    c = S.cartas[k] = { agente: agente, ruta: x.ruta, titulo: x.titulo || '', info: null, img: '', menu: '' };
    c.n = nodo('div', 'wsm-ent');
    c.arr = nodo('div', 'wsm-ent-arr');                       /* lo que se toma para arrastrar: miniatura y nombre */
    c.mini = nodo('div', 'wsm-ent-mini');
    c.tx = nodo('div', 'tx');
    c.arr.appendChild(c.mini); c.arr.appendChild(c.tx);
    c.chips = nodo('div', 'chips');
    c.menuN = nodo('div', 'wsm-ent-menu'); c.menuN.hidden = true;
    c.pista = nodo('small', 'wsm-ent-pista', '⠿ Arrástralo a Mail, Slack o una carpeta');
    c.mini.appendChild(c.pista);
    c.hace = nodo('div', 'wsm-ent-hace'); c.hace.hidden = true;
    c.cambios = nodo('div', 'wsm-ent-cambios');
    [c.arr, c.chips, c.menuN, c.hace, c.cambios].forEach(function (p) { c.n.appendChild(p); });
    c.n.title = '';
    pintarCarta(c);
    host({ op: 'entrega', agente: agente, ruta: x.ruta });
    return c.n;
  }
  function pintarCarta(c) {
    var r = (c.info && c.info.actual) || c.ruta, e = (c.info && c.info.ext) || ext(r), nom = (c.info && c.info.nombre) || base(r);
    var v = c.info && c.info.version ? 'v' + c.info.version : '';
    var fk = [c.img, e, c.w, c.h].join('|');
    if (c.mini._k !== fk) {
      var cruce = [].slice.call(c.mini.children || []).filter(function (x) { return x.className === 'wsm-cruce'; });
      c.mini._k = fk; c.mini.textContent = ''; c.mini.appendChild(c.pista);
      c.mini.classList.toggle('foto', !!c.img && !!c.foto);
      c.mini.classList.toggle('ancha', !!c.img && !!c.foto && (c.w || 0) > (c.h || 0) * 1.15);
      c.mini.style.setProperty('--e', COLOR_EXT[e] || '#6b6b78');
      if (c.img) { var im = nodo('img'); im.src = c.img; im.alt = ''; im.draggable = false; c.mini.appendChild(im); }
      if (e && !(c.img && c.foto)) c.mini.appendChild(nodo('b', 'ext', e.toUpperCase()));
      else if (e) c.mini.appendChild(nodo('b', 'ext chica', e.toUpperCase()));
      cruce.forEach(function (x) { c.mini.appendChild(x); });
    }
    var tk = [c.titulo, nom, v, c.info && c.info.tam].join('|');
    if (c.tx._k !== tk) {
      c.tx._k = tk; c.tx.textContent = '';
      c.tx.appendChild(nodo('b', null, c.titulo || nom));
      c.tx.appendChild(nodo('small', null, [c.titulo ? nom : '', tam(c.info && c.info.tam), v].filter(Boolean).join(' · ')));
      c.tx.title = r;
    }
    if (!c.chips.firstChild) {
      c.chips.appendChild(boton('chip p', 'Abrir', function () { pedir(c, 'abierto', { op: 'entrega_abrir', agente: c.agente, ruta: cual(c), modo: 'abrir' }); }));
      c.chips.appendChild(boton('chip', 'Vista rápida', function () { pedir(c, 'vista', { op: 'entrega_vista', agente: c.agente, ruta: cual(c) }); }));
      c.chips.appendChild(boton('chip', 'Mandar a…', function (b) { menu(c, 'mandar', b); }));
      c.chips.appendChild(boton('chip wsm-mas', '⋯', function (b) { menu(c, 'mas', b); }));
      c.chips.children[2].setAttribute('aria-haspopup', 'true');
    }
    c.pista.hidden = !enApp();
    pintarHaciendo(c);
    if (!c.cambios.firstChild) {
      c.cambios.appendChild(nodo('small', null, 'Pedir cambios'));
      CAMBIOS.forEach(function (t) { c.cambios.appendChild(boton('chip', t, function () { pedirCambio(c, t); })); });
      c.cambios.appendChild(boton('chip', 'Otro…', function () { otroCambio(c); }));
    }
  }
  /* la ruta que enseña ahora (la versión elegida) */
  function cual(c) { return (c.info && c.info.actual) || c.ruta; }
  function alEntrega(ev) {
    var c = S.cartas[clave(ev.agente, ev.ruta)];
    if (!c) { var g = S.porRuta && S.porRuta[clave(ev.agente, ev.ruta)]; if (g) g(ev); return; }
    if (ev.mal) { c.mal = true; acomodar(function () { pintarCarta(c); }); return; }
    c.info = ev;
    acomodar(function () { pintarCarta(c); });
  }
  function miniatura(d) {
    var c = S.cartas[clave(d.agente, d.ruta)];
    if (c) {
      if (c.img && c.img !== d.img) cruzar(c.mini);            /* otra versión: la imagen de antes se desvanece encima */
      c.img = d.img; c.foto = !!d.foto; c.w = +d.w || 0; c.h = +d.h || 0; acomodar(function () { pintarCarta(c); });
    }
    var f = S.filas && S.filas[clave(d.agente, d.ruta)];
    if (f) { f.img = d.img; f.foto = !!d.foto; if (S.grande.abierto) pintarGrande(); }
  }
  /* «Mandar a…» y «⋯»: un menú dentro de la tarjeta (se desliza) */
  function menu(c, cual_, b) {
    c.menu = c.menu === cual_ ? '' : cual_;
    if (!c.menuN.hidden) fantasma(c.menuN);                 /* el de antes se desvanece en su lugar */
    acomodar(function () {
      c.menuN.textContent = ''; c.menuN.hidden = !c.menu;
      if (!c.menu) return;
      var ruta = cual(c), r = rect(b);
      var filas = c.menu === 'mandar' ? [
        ['Correo nuevo, con el archivo', 'Tú lo envías', function () { pedir(c, 'correo', { op: 'entrega_correo', agente: c.agente, ruta: ruta }); }],
        ['Compartir…', 'AirDrop, Mensajes, Notas…', function () { pedir(c, 'compartir', { op: 'entrega_compartir', agente: c.agente, ruta: ruta, rect: r }); }],
        ['Pásaselo a otro agente…', 'Lo trabaja en su conversación', function () { elegirAgente(c); }],
        ['Copiar el archivo', 'Para pegarlo donde quieras', function () { pedir(c, 'copiado', { op: 'entrega_copiar', agente: c.agente, ruta: ruta }); }]
      ] : [
        ['Copiar el archivo', '', function () { pedir(c, 'copiado', { op: 'entrega_copiar', agente: c.agente, ruta: ruta }); }],
        ['Mostrar en Finder', '', function () { pedir(c, 'revelado', { op: 'entrega_abrir', agente: c.agente, ruta: ruta, modo: 'revelar' }); }],
        ['Guardar en…', 'Una copia donde elijas', function () { pedir(c, 'guardado', { op: 'entrega_guardar', agente: c.agente, ruta: ruta }); }]
      ];
      filas.forEach(function (f) {
        var i = boton('wsm-item', null, function () { var keep = f[0].indexOf('Pásaselo') === 0; if (!keep) { c.menu = ''; fantasma(c.menuN); acomodar(function () { c.menuN.hidden = true; c.menuN.textContent = ''; }); } f[2](); });
        i.appendChild(nodo('span', null, f[0])); if (f[1]) i.appendChild(nodo('small', null, f[1]));
        c.menuN.appendChild(i);
      });
      if (c.menu === 'mas' && c.info && (c.info.versiones || []).length > 1) {
        c.menuN.appendChild(nodo('div', 'wsm-sep', 'Versiones'));
        c.info.versiones.slice().reverse().forEach(function (v) {
          var i = boton('wsm-item' + (v.ruta === ruta ? ' on' : ''), null, function () { verVersion(c, v.ruta); });
          i.appendChild(nodo('span', null, 'v' + v.v + (v.ruta === ruta ? ' · esta' : ''))); i.appendChild(nodo('small', null, v.nombre + ' · ' + hace(v.t)));
          c.menuN.appendChild(i);
        });
      }
      entra(c.menuN);
    });
    if (c.menu) aLaVistaN(c.menuN);
  }
  /* un menú que se abre dentro de la burbuja queda a la vista (la burbuja se recorre, la página no) */
  function aLaVistaN(n) {
    setTimeout(function () { try { if (n.scrollIntoView && !n.hidden) n.scrollIntoView({ block: 'nearest', behavior: WSM.quieto() ? 'auto' : 'smooth' }); } catch (e) { } }, 230);
  }
  function verVersion(c, ruta) {
    c.menu = '';
    S.porRuta = S.porRuta || {};
    S.porRuta[clave(c.agente, ruta)] = function (ev) {
      delete S.porRuta[clave(c.agente, ruta)];
      if (ev.mal) return;
      S.cartas[clave(c.agente, ruta)] = c;        /* la misma tarjeta: su miniatura llega por esta ruta */
      c.info = ev;                                 /* la miniatura de antes se queda hasta que llega la nueva */
      if (!c.menuN.hidden) fantasma(c.menuN);
      acomodar(function () { c.menuN.hidden = true; c.menuN.textContent = ''; pintarCarta(c); });
    };
    host({ op: 'entrega', agente: c.agente, ruta: ruta });
  }
  /* «Pedir cambios»: la v2 en la misma tarjeta (un encargo con la base; la página nombra la versión nueva) */
  function pedirCambio(c, t) {
    var ref = 'c' + Math.random().toString(36).slice(2, 10);
    c.cambio = { ref: ref, texto: t, id: '' };
    host({ op: 'encargar', agente: c.agente, pedido: t, base: cual(c), ref: ref });
    acomodar(function () { pintarHaciendo(c); });
  }
  function otroCambio(c) {
    acomodar(function () {
      c.cambios.textContent = '';
      var ta = nodo('input', 'wsm-in'); ta.placeholder = '¿Qué le cambio?'; ta.maxLength = 300;
      ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && ta.value.trim()) { e.preventDefault(); var v = ta.value.trim(); c.cambios.textContent = ''; pedirCambio(c, v); pintarCarta(c); } });
      c.cambios.appendChild(ta);
      c.cambios.appendChild(boton('chip p', 'Pedir', function () { if (ta.value.trim()) { var v = ta.value.trim(); c.cambios.textContent = ''; pedirCambio(c, v); pintarCarta(c); } }));
      try { ta.focus(); } catch (e) { }
    });
  }
  function pintarHaciendo(c) {
    var e = c.cambio && c.cambio.id ? encargo(c.agente, c.cambio.id) : null, ver = !!c.cambio;
    var k = ver ? [c.cambio.texto, e && e.estado, e && e.pasos && e.pasos.i].join('|') : '';
    if (c.hace._k === k) return;
    if (!c.hace.hidden && c.hace.firstChild && (!ver || (e && e.estado === 'listo'))) fantasma(c.hace);
    c.hace._k = k; c.hace.textContent = ''; c.hace.hidden = !ver;
    if (!ver) return;
    if (e && e.estado === 'listo') {
      /* la versión nueva: la que pidió la página (destino) o una del mismo archivo (…_v3.md); nunca otro archivo que
         el agente haya enseñado de paso (lo encontró la prueba en vivo: la tarjeta se cambiaba a otra entrega) */
      var tronco = function (r) { return base(r).replace(/\.[^.]+$/, '').replace(/_v\d+$/i, '').toLowerCase(); };
      var nueva = (e.archivos || []).filter(function (a) { return a.ruta === e.destino; })[0]
        || (e.archivos || []).filter(function (a) { return tronco(a.ruta) === tronco(cual(c)) && a.ruta !== cual(c); })[0];
      c.cambio = null; c.deEncargo = true;
      visto(c.agente, e.id);
      if (nueva) { c.hace.hidden = true; verVersion(c, nueva.ruta); return; }
      c.hace.hidden = false; c.hace.appendChild(nodo('small', null, 'Terminó sin una versión nueva de este archivo. En la página ves qué hizo.'));
      return;
    }
    var v = c.info && c.info.version ? c.info.version + 1 : 2;
    var t = e && (e.estado === 'error' || e.estado === 'interrumpido' || e.estado === 'parado')
      ? 'No salió la v' + v + ' (' + ESTADO_TXT[e.estado] + ').' : 'Haciendo la v' + v + ' · «' + c.cambio.texto + '»';
    c.hace.appendChild(barras(e && e.pasos, !e || e.estado !== 'trabajando'));
    c.hace.appendChild(nodo('small', null, t));
  }
  function barras(p, quieto) {
    var b = nodo('div', 'barras' + (quieto ? ' quieto' : '')), n = p ? p.n : 3, i = p ? p.i : 0;
    for (var j = 0; j < n; j++) b.appendChild(nodo('b', j < i ? 'h' : j === i && !quieto ? 'a' : ''));
    return b;
  }

  /* ---------- «Pásaselo a…»: otro agente y una nota ---------- */
  function elegirAgente(c, desdeBarra) {
    var otros = ((s() && s().agentes) || []).filter(function (a) { return a.id !== (c ? c.agente : s().elegido); });
    var cont = c ? c.menuN : R.menuB;
    acomodar(function () {
      cont.textContent = ''; cont.hidden = false;
      if (!otros.length) { cont.appendChild(nodo('small', 'wsm-vacio', 'No tienes otro agente todavía.')); return; }
      cont.appendChild(nodo('div', 'wsm-sep', '¿A quién se lo paso?'));
      var fila = nodo('div', 'wsm-ags-p'), elegido = { id: otros[0].id };
      otros.forEach(function (a) {
        var b = boton('wsm-ag-p' + (a.id === elegido.id ? ' on' : ''), null, function () {
          elegido.id = a.id; [].forEach.call(fila.children, function (x) { x.classList.toggle('on', x === b); });
        });
        b.style.setProperty('--c', a.c);
        try { b.appendChild(monito(a.c, a.f, 22, { quieto: true })); } catch (e) { }
        b.appendChild(nodo('span', null, a.n)); fila.appendChild(b);
      });
      cont.appendChild(fila);
      var nota = nodo('input', 'wsm-in'); nota.placeholder = '¿Qué hace con él? (opcional)'; nota.maxLength = 600;
      cont.appendChild(nota);
      /* Fable v2: el otro agente lo trabaja con el nivel de ESTE encargo (no con el de su página) y la tarjeta lo dice */
      var info = nodo('div', 'wsm-pasa-nivel'), pasa;
      cont.appendChild(info);
      function pintarNivel() {
        var a = ag(elegido.id) || {}, n = a.encargo;
        elegido.elige = elegido.elige || {};
        info.textContent = '';
        if (!n) return;
        var t = nodo('div', 'filas');
        t.appendChild(nodo('span', 'k', 'Puede')); var v = nodo('span', 'v largo'); v.appendChild(nodo('b', null, puedeDe(n, elegido.elige))); t.appendChild(v);
        var ll = a.lo_lee || [];
        if (ll[0]) { t.appendChild(nodo('span', 'k', 'Lo lee')); var w = nodo('span', 'v largo'); w.appendChild(nodo('b', null, ll[0])); if (ll[1]) w.appendChild(nodo('small', null, ll[1])); t.appendChild(w); }
        info.appendChild(t);
        info.appendChild(bloqueNivel(n, elegido.elige, pintarNivel));
        if (pasa) pasa.disabled = bloqueado(n, elegido.elige);
      }
      [].forEach.call(fila.children, function (x, i) {
        var viejo = x.onclick;
        x.onclick = function (ev) { viejo(ev); if (elegido.id !== elegido.antes) { elegido.antes = elegido.id; elegido.elige = {}; } pintarNivel(); };
      });
      var ch = nodo('div', 'chips');
      ch.appendChild(pasa = boton('chip p', 'Pásaselo', function () {
        var n = (ag(elegido.id) || {}).encargo;
        if (bloqueado(n, elegido.elige)) return;                 /* sin elegir su nivel, no se pasa */
        var ref = 'x' + Math.random().toString(36).slice(2, 10), op;
        if (c) op = { op: 'pasar', agente: c.agente, a: elegido.id, ruta: cual(c), nota: nota.value.trim(), ref: ref };
        else if (S.frente.adjunto) op = { op: 'pasar', agente: s().elegido, a: elegido.id, ruta: S.frente.adjunto, nota: nota.value.trim(), ref: ref };
        else op = { op: 'pasar_frente', agente: s().elegido, a: elegido.id, nota: nota.value.trim(), ref: ref };
        if (n) conNivel(op, n, elegido.elige);
        S.pasando = { ref: ref, a: elegido.id, cont: cont, carta: c };
        host(op);
        acomodar(function () { cont.textContent = ''; cont.appendChild(nodo('small', 'wsm-ok', 'Se lo paso a ' + nombre(elegido.id) + '…')); });
      }));
      ch.appendChild(boton('chip', 'Cancelar', function () { if (c) c.menu = ''; acomodar(function () { cont.textContent = ''; cont.hidden = true; }); }));
      cont.appendChild(ch);
      elegido.antes = elegido.id;
      pintarNivel();
      entra(cont);
    });
    aLaVistaN(cont);
  }
  function alPasado(ev) {
    var p = S.pasando; if (!p || p.ref !== ev.ref) return;
    S.pasando = null;
    acomodar(function () {
      p.cont.textContent = '';
      p.cont.appendChild(nodo('small', ev.ok ? 'wsm-ok' : 'wsm-mal', ev.ok ? 'Listo: ' + nombre(ev.a) + ' ya lo tiene. Te toca su monito al terminar.'
        : 'No se lo pude pasar: ' + (ev.texto || 'inténtalo otra vez.')));
    });
    setTimeout(function () { if (p.carta) p.carta.menu = ''; acomodar(function () { p.cont.textContent = ''; p.cont.hidden = true; }); }, 3500);
  }

  /* ---------- la tarjeta de encargo (la arma la app) y su avance ---------- */
  function propuesta(d) {
    if (!d || !d.id) return;
    S.propuestas[d.id] = d;
    seguir(d.id);
    try { var m = WSM.mono(); if (m && !WSM.quieto()) { m.salta(.7); if (m.signo) m.signo('pregunta', { donde: 'der', esc: .8 }); } } catch (e) { }
    abrirGlobo();
  }
  function decidir(id, d) {
    var p = S.propuestas[id]; if (!p) return;
    if (d === 'encargar' && bloqueado(p.nivel, p.elige)) return;     /* sin elegir su nivel, Encargar no hace nada */
    if (d === 'encargar' && p.editable && !recado(p).trim()) return;  /* sin recado, tampoco */
    p.decidiendo = d;
    var op = { op: 'encargo_decidir', id: id, decision: d };
    if (d === 'encargar' && p.nivel) conNivel(op, p.nivel, p.elige);
    if (d === 'encargar' && p.editable) op.pedido = recado(p).trim().slice(0, 1000);
    host(op);
    acomodar(pintarEncs);
  }
  /* ---------- Fable v2: el nivel de ESTE encargo (las piezas las arma la app; aquí solo se juntan) ---------- */
  function puedeDe(n, el_) {
    el_ = el_ || {};
    if (!n) return '';
    if (!n.acotado) return n.pagina || '';
    var mas = [];
    if (el_.comandos && n.comandos) mas.push(n.comandos);
    if (el_.internet && n.internet) mas.push(n.internet);
    return n.base + (mas.length ? '; también ' + mas.join(' y ') : '; ' + n.sin);
  }
  function bloqueado(n, el_) { return !!(n && !n.acotado && !(el_ || {}).como_pagina); }
  /* Fable v2 §2.1: el recado (tus últimos mensajes) y lo que le cambiaste en la tarjeta */
  function recado(p) { S.editados = S.editados || {}; return S.editados[p.id] != null ? S.editados[p.id] : (p.pedido_completo || p.pedido || ''); }
  function conNivel(op, n, el_) {
    (n.casillas || []).forEach(function (c) { op[c[0]] = !!(el_ || {})[c[0]]; });
    return op;
  }
  /* las casillas (una por cosa que se sube) y, si su motor no se acota, por qué */
  function bloqueNivel(n, el_, alCambiar) {
    var b = nodo('div', 'wsm-nivel');
    if (n.aviso) b.appendChild(nodo('small', 'aviso', n.aviso));
    (n.casillas || []).forEach(function (c) {
      var on = !!el_[c[0]];
      var x = boton('casilla' + (on ? ' on' : ''), c[1], function () { el_[c[0]] = !el_[c[0]]; alCambiar(); });
      x.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.appendChild(x);
    });
    return b;
  }
  function decidido(d) {
    var p = S.propuestas[d.id]; if (!p) return;
    p.decision = d.decision;
    if (d.decision === 'encargar') { p.encargando = true; acomodar(pintarEncs); return; }
    dejar(d.id);
    if (d.decision === 'aqui' && !d.esperaba) { try { WSM.decir('Mejor dímelo aquí, en corto.'); } catch (e) { } }
  }
  /* la app ya mandó el encargo: la tarjeta se vuelve su avance (el mismo nodo: no vuelve a entrar) */
  function alEncargo(ev) {
    if (ev.ok && ev.id) S.refs[ev.ref] = ev.id;
    var p = S.propuestas[ev.ref];
    if (p) {
      if (!ev.ok) { p.error = ev.texto || 'No salió.'; p.encargando = false; acomodar(pintarEncs); return; }
      var n = S.nodos[ev.ref]; delete S.nodos[ev.ref]; S.nodos[ev.id] = n;
      var i = S.siguiendo.indexOf(ev.ref); if (i >= 0) S.siguiendo[i] = ev.id; else seguir(ev.id);
      delete S.propuestas[ev.ref];
      S.enCurso = S.enCurso || {}; S.enCurso[ev.id] = { titulo: p.titulo || '', agente: p.agente, pedido: p.pedido };
      acomodar(pintarEncs);
      return;
    }
    for (var k in S.cartas) {                                 /* un «Pedir cambios» de esa tarjeta */
      var c = S.cartas[k];
      if (c.cambio && c.cambio.ref === ev.ref) {
        if (!ev.ok) { c.cambio.fallo = ev.texto || 'No salió.'; }
        else c.cambio.id = ev.id;
        acomodar(function () { pintarHaciendo(c); });
        return;
      }
    }
  }
  function encargo(agente, id) { var l = S.encargos[agente] || []; for (var i = 0; i < l.length; i++) if (l[i].id === id) return l[i]; return null; }
  function buscar(id) { for (var a in S.encargos) { var e = encargo(a, id); if (e) return e; } return null; }
  function seguir(id) { if (S.siguiendo.indexOf(id) < 0) S.siguiendo.push(id); }
  function dejar(id) {
    var i = S.siguiendo.indexOf(id); if (i >= 0) S.siguiendo.splice(i, 1);
    delete S.propuestas[id];
    var n = S.nodos[id]; delete S.nodos[id];
    if (n && n.parentNode) quitar(n, 220, function () { n.remove(); afinar(); });
    else afinar();
  }
  function afinar() { if (R.encs) R.encs.hidden = !R.encs.firstChild; try { if (!hay()) WSM.pintarGlobo(); } catch (e) { } }
  /* lo del elegido que se ve en la burbuja */
  function visibles() {
    var el_ = s() ? s().elegido : '';
    return S.siguiendo.filter(function (id) {
      var p = S.propuestas[id]; if (p) return p.agente === el_;
      var e = buscar(id); return e ? e.agente_ === el_ : (S.enCurso && S.enCurso[id] && S.enCurso[id].agente === el_);
    });
  }
  function hay() { return visibles().length > 0; }
  function pintarEncs() {
    if (!R.encs || (R.w.globo && R.w.globo._sale)) return;   /* mientras la burbuja sale, nada cambia dentro */
    var ids = visibles();
    ids.forEach(function (id, k) {
      var n = S.nodos[id], nuevo = !n;
      if (nuevo) { n = S.nodos[id] = nodo('div', 'wsm-enc'); }
      if (S.propuestas[id]) pintarPropuesta(n, S.propuestas[id]); else pintarEncargo(n, id);
      if (n.parentNode !== R.encs) { R.encs.appendChild(n); if (nuevo) entra(n); }
    });
    [].slice.call(R.encs.children || []).forEach(function (n) {
      var vivo = ids.some(function (id) { return S.nodos[id] === n; });
      if (vivo || /saliendo/.test(n.className)) return;
      if (!S.rancio) fantasma(n);             /* se desvanece en su lugar; lo de una burbuja que ya se cerró, no */
      n.remove();
    });
    S.rancio = false;
    R.encs.hidden = !R.encs.firstChild;
    if (R.w && R.w.globo) R.w.globo.classList.toggle('con-prop', ids.some(function (id) { return !!S.propuestas[id]; }));
  }
  function pintarPropuesta(n, p) {
    var k = 'p|' + JSON.stringify(p);
    if (n._k === k) return;
    n._k = k; n.textContent = ''; n.className = 'wsm-enc prop';
    var cab = nodo('div', 'cab'); cab.appendChild(candado()); cab.appendChild(nodo('b', null, p.cab || 'Encargo · con tu OK'));
    cab.appendChild(boton('wsm-cx', '×', function () { decidir(p.id, 'no'); }));
    n.appendChild(cab);
    n.appendChild(nodo('p', 'quien', p.quien || ''));
    if (p.editable && !p.encargando) {
      var ed = nodo('textarea', 'pedido-ed'); ed.rows = 3; ed.maxLength = 1000; ed.spellcheck = false;
      ed.value = recado(p);
      ed.setAttribute('aria-label', 'Lo que se encarga (puedes cambiarlo)');
      ed.addEventListener('input', function () {
        S.editados[p.id] = ed.value;
        var vacio = !ed.value.trim();
        (clasesEn(n, 'chip') || []).forEach(function (b) { if (b._enc) b.disabled = vacio || bloqueado(p.nivel, p.elige) || !!p.decidiendo; });
      });
      n.appendChild(ed);
      n.appendChild(nodo('small', 'nota', 'Es lo que le llega: tus últimos mensajes. Cámbialo si quieres.'));
    } else n.appendChild(nodo('blockquote', 'pedido', '«' + (p.encargando && p.editable ? recado(p) : (p.pedido || '')) + '»'));
    var t = nodo('div', 'filas');
    p.elige = p.elige || {};
    (p.filas || []).forEach(function (f) {
      var puede = f[0] === 'Puede' && p.nivel;
      t.appendChild(nodo('span', 'k', f[0]));
      var v = nodo('span', 'v' + (puede || f[0] === 'Lo lee' ? ' largo' : ''));
      v.appendChild(nodo('b', null, puede ? puedeDe(p.nivel, p.elige) : f[1])); if (f[2]) v.appendChild(nodo('small', null, f[2])); t.appendChild(v);
    });
    n.appendChild(t);
    if (p.nivel && !p.encargando) n.appendChild(bloqueNivel(p.nivel, p.elige, function () { n._k = ''; pintarPropuesta(n, p); }));
    if (p.formato && !(p.elige && p.elige.comandos)) n.appendChild(nodo('small', 'nota', p.formato));
    if (p.error) n.appendChild(nodo('small', 'wsm-mal', p.error));
    var ch = nodo('div', 'chips');
    if (p.encargando) ch.appendChild(nodo('small', 'wsm-ok', 'Se lo paso para que lo haga en segundo plano…'));
    else (p.botones || []).forEach(function (b) {
      var e = boton('chip' + (b[2] ? ' p' : ''), b[0], function () { decidir(p.id, b[1]); });
      if (b[1] === 'encargar') e._enc = true;
      if (p.decidiendo || (b[1] === 'encargar' && (bloqueado(p.nivel, p.elige) || (p.editable && !recado(p).trim())))) e.disabled = true;
      ch.appendChild(e);
    });
    n.appendChild(ch);
    if (p.nota) n.appendChild(nodo('small', 'nota', p.nota));
  }
  function clasesEn(n, c) {
    var out = [];
    (function rec(x) { (x.children || []).forEach(function (h) { if ((' ' + (h.className || '') + ' ').indexOf(' ' + c + ' ') >= 0) out.push(h); rec(h); }); })(n);
    return out;
  }
  function candado() {
    if (!document.createElementNS) return nodo('i', 'ico');
    var NS = 'http://www.w3.org/2000/svg', sv = document.createElementNS(NS, 'svg');
    sv.setAttribute('viewBox', '0 0 9 9'); sv.setAttribute('width', '15'); sv.setAttribute('height', '15'); sv.setAttribute('class', 'ico');
    [[2, 1, 5, 1], [2, 2, 1, 2], [6, 2, 1, 2], [1, 4, 7, 4]].forEach(function (r) { var q = document.createElementNS(NS, 'rect'); q.setAttribute('x', r[0]); q.setAttribute('y', r[1]); q.setAttribute('width', r[2]); q.setAttribute('height', r[3]); sv.appendChild(q); });
    return sv;
  }
  function pintarEncargo(n, id) {
    var e = buscar(id), c = S.enCurso && S.enCurso[id];
    var k = 'e|' + JSON.stringify(e || c || {});
    if (n._k === k) return;
    n._k = k; n.textContent = ''; n.className = 'wsm-enc' + (e && e.estado === 'necesita' ? ' necesita' : '');
    var estado = e ? e.estado : 'en_cola', agente = e ? e.agente_ : c.agente;
    var cab = nodo('div', 'cab'); var pt = nodo('i', 'pt'); pt.style.setProperty('--c', (ag(agente) || {}).c || '#fff'); cab.appendChild(pt);
    cab.appendChild(nodo('b', null, nombre(agente))); cab.appendChild(nodo('span', 'est', ESTADO_TXT[estado] || estado));
    cab.appendChild(boton('wsm-cx', '×', function () { dejar(id); if (e && (estado === 'listo' || estado === 'error')) visto(agente, id); }));
    n.appendChild(cab);
    n.appendChild(nodo('p', 'titulo', (e && e.titulo) || (c && c.titulo) || (e && e.pedido) || ''));
    if (estado === 'trabajando' || estado === 'en_cola') {
      var ps = nodo('div', 'wsm-pasos'); ps.appendChild(barras(e && e.pasos, estado === 'en_cola'));
      var p = e && e.pasos;
      ps.appendChild(nodo('small', null, p ? 'Paso ' + Math.min(p.i + 1, p.n) + ' de ' + p.n + (p.texto ? ' · ' + p.texto : '') : estado === 'en_cola' ? 'Empieza en cuanto termine lo que está haciendo' : 'Empezando…'));
      n.appendChild(ps);
      var ch = nodo('div', 'chips');
      ch.appendChild(boton('chip', 'Ver en la página', function () { host({ op: 'ver_pagina', agente: agente }); }));
      ch.appendChild(boton('chip', 'Parar', function (b) { b.disabled = true; host({ op: 'encargo', agente: agente, id: id, accion: 'parar' }); }));
      n.appendChild(ch);
      n.appendChild(nodo('small', 'nota', 'Puedes cerrar esto y seguir con lo tuyo: te toco cuando termine.'));
    } else if (estado === 'necesita') {
      var q = e.permiso || e.pregunta;
      n.appendChild(nodo('p', 'pide', e.permiso ? (e.permiso.texto || 'Quiere usar una de sus herramientas.') : (q.texto || '')));
      var ch2 = nodo('div', 'chips');
      if (e.permiso) (e.permiso.opciones || ['permitir', 'negar']).forEach(function (o) {
        var t = o === 'permitir_turno' ? ((e.permiso.grupo && e.permiso.grupo.texto) || 'Sí, y lo parecido en este trabajo')
          : { permitir: 'Permitir', permitir_siempre: 'Siempre', negar: 'No' }[o] || o;
        ch2.appendChild(boton('chip' + (o === 'permitir' ? ' p' : ''), t, function (b) {
          (clasesEn(ch2, 'chip') || []).forEach(function (x) { x.disabled = true; });
          b.textContent = o === 'negar' ? 'Listo, no lo hará' : 'Listo, le di permiso';
          host({ op: 'encargo_permiso', agente: agente, id: e.permiso.id, decision: o });
        }));
      });
      else if ((q.opciones || []).length) q.opciones.forEach(function (o, i) { ch2.appendChild(boton('chip' + (i ? '' : ' p'), o, function (b) { b.disabled = true; host({ op: 'encargo_responder', agente: agente, id: q.id, texto: o }); })); });
      else ch2.appendChild(boton('chip', 'Ver en la página', function () { host({ op: 'ver_pagina', agente: agente }); }));
      n.appendChild(ch2);
      if (e.permiso) n.appendChild(nodo('small', 'nota', 'Lo pide mientras trabaja en tu encargo' + (e.permiso.leyo_archivo ? ' después de leer «' +
        e.permiso.leyo_archivo + '» (lo escribieron otros)' : '') + '. Solo pasa si tú lo eliges.'));
    } else {
      if (e && e.resumen) n.appendChild(nodo('p', 'res', e.resumen));
      if (e && e.error) n.appendChild(nodo('small', 'wsm-mal', e.error));
      (e && e.archivos || []).forEach(function (a) { n.appendChild(tarjeta(a, agente)); S.cartas[clave(agente, a.ruta)].deEncargo = true; });
      if (estado === 'listo' && !(e.archivos || []).length) n.appendChild(nodo('small', 'nota', 'Terminó, pero no dejó un archivo. En la página ves qué hizo.'));
      var ch3 = nodo('div', 'chips');
      if (estado !== 'listo') ch3.appendChild(boton('chip p', 'Reintentar', function (b) { b.disabled = true; host({ op: 'encargo', agente: agente, id: id, accion: 'reintentar' }); }));
      ch3.appendChild(boton('chip', 'Ver en la página', function () { host({ op: 'ver_pagina', agente: agente }); }));
      n.appendChild(ch3);
      if (e && !e.visto && !(S.vistoLocal || {})[id]) visto(agente, id);
    }
  }

  /* ---------- los encargos de cada agente: el avance y el toque ---------- */
  function alEncargos(agente, lista) {
    lista.forEach(function (e) { e.agente_ = agente; });
    var antes = S.cargado[agente];
    S.encargos[agente] = lista;
    S.cargado[agente] = true;
    lista.forEach(function (e) {
      var prev = S.vistos[e.id];
      S.vistos[e.id] = e.estado;
      if (!antes || prev === e.estado) return;
      if ((e.estado === 'listo' || e.estado === 'necesita') && !e.visto && !aLaVista(e.id)) tocar(agente, e);
      if (e.estado === 'listo' && aLaVista(e.id)) visto(agente, e.id);
    });
    var conCambio = []; for (var k in S.cartas) if (S.cartas[k].cambio && conCambio.indexOf(S.cartas[k]) < 0) conCambio.push(S.cartas[k]);
    if (conCambio.length) acomodar(function () { conCambio.forEach(pintarHaciendo); });
    pintarInsignia();
    if (hay() || R.encs && R.encs.firstChild) acomodar(pintarEncs);
    if (S.grande.abierto) pintarGrande();
  }
  /* ¿ya lo estás viendo? (su tarjeta en la burbuja abierta, o el «Pedir cambios» de una tarjeta a la vista) */
  function aLaVista(id) {
    try {
      if (WSM.piezas().globo.hidden) return false;
      if (visibles().indexOf(id) >= 0) return true;
      for (var k in S.cartas) { var c = S.cartas[k]; if (c.cambio && c.cambio.id === id && c.n.offsetParent) return true; }
    } catch (e) { }
    return false;
  }
  /* «ya lo viste»: a la página y aquí mismo (el número del nido no espera a la vuelta de la foto) */
  function visto(agente, id) { S.vistoLocal = S.vistoLocal || {}; S.vistoLocal[id] = 1; host({ op: 'encargo', agente: agente, id: id, accion: 'visto' }); }
  function pendientes() {
    var n = 0;
    var v = S.vistoLocal || {};
    for (var a in S.encargos) (S.encargos[a] || []).forEach(function (e) { if ((e.estado === 'listo' && !e.visto && !v[e.id]) || e.estado === 'necesita') n++; });
    for (var k in S.esperan) if (S.esperan[k]) n++;           /* lo de otros que te espera (A0: su tarjeta de OK) */
    return n;
  }
  /* lo que no es un encargo y te espera (A0: la tarjeta de OK de la app abierta) suma al MISMO número del nido */
  function cuenta(clave, espera) {
    S.esperan = S.esperan || {};
    if (!!S.esperan[clave] === !!espera) return;
    if (espera) S.esperan[clave] = 1; else delete S.esperan[clave];
    pintarInsignia();
  }
  function pintarInsignia() {
    if (S.grande.abierto) pintarGrande();                  /* «Te esperan» y los números de la tira, al día */
    var I = R.insignia; if (!I) return;
    var n = pendientes(), t = n > 9 ? '9+' : String(n);
    if (!n) {                                 /* se va desvaneciéndose (antes se apagaba de golpe) */
      if (I.hidden || I._sale) return;
      quitar(I, 200, function () { I.hidden = true; });
      return;
    }
    var volvio = !!I._sale;
    if (volvio) I._sale();
    if (I.textContent === t && !I.hidden && !volvio) return;
    var era = I.hidden || volvio;
    I.textContent = t; I.hidden = false;
    if (era) entra(I);
  }
  /* EL toque (uno solo para todo lo que te llama: un encargo que terminó o te necesita, y lo de actuar de A0 —su OK y
     su aviso tranquilo—): el brinco del monito según qué es, el globito junto al nido y el número. Nunca toma el
     teclado ni suena. Un globito a la vez: lo nuevo se cruza encima del de antes (sin salir y volver a entrar). */
  function gesto(tipo) {
    try {
      var m = WSM.mono(); if (!m || WSM.quieto()) return;
      if (tipo === 'necesita') { m.salta(.8); if (m.signo) m.signo('pregunta', { donde: 'der', esc: .8 }); }
      else if (tipo === 'termino') { m.salta(1.05); if (m.rafaga) m.rafaga(5); }
    } catch (x) { }
  }
  /* d: {clave, agente, tipo: 'termino'|'necesita'|'aviso' (sin brinco), titulo, sub, chips: [[texto, fn, primario]],
         ensayo (lavanda), largo (el texto se parte en renglones), ms (lo que se queda; el ratón encima lo detiene)} */
  function toque(d) {
    if (!R.toque || !d) return;
    S.toque = { clave: String(d.clave || ''), agente: d.agente || '' };
    if (!d.gestoHecho) gesto(d.tipo);
    d.gestoHecho = true;
    var T = R.toque, ya = !T.hidden && !T._sale;
    /* si ya va saliendo para dejar entrar a otro, el que entra es este (el último) */
    if (S.toqueSig) { S.toqueSig = d; return; }
    /* otro tamaño (el globito de una línea ↔ el aviso con renglones y botones): el de antes sale entero y luego entra
       el nuevo. Cruzarlos en su lugar daba un brinco de tamaño (la copia que se desvanece se iba con la orilla). */
    var largo = !!(ya && T.firstChild && T.firstChild.classList && T.firstChild.classList.contains('largo'));
    if (ya && largo !== !!d.largo && !WSM.quieto()) {
      S.toqueSig = d;
      clearTimeout(S.relojToque);
      quitar(T, 240, function () {
        T.hidden = true; T.textContent = '';
        var x = S.toqueSig; S.toqueSig = null;
        if (x) toque(x);
      });
      return;
    }
    var a = ag(d.agente) || { c: d.color || '#b9a3ff' };
    var vieja = ya ? T.firstChild : null, anchoVieja = vieja ? vieja.offsetWidth : 0;
    var cuerpo = nodo('div', 'in' + (d.largo ? ' largo' : '') + (d.ensayo ? ' ensayo' : ''));
    var pt = nodo('i', 'pt'); pt.style.setProperty('--c', a.c); cuerpo.appendChild(pt);
    var tx = nodo('div', 'tx'); tx.appendChild(nodo('b', null, String(d.titulo || ''))); if (d.sub) tx.appendChild(nodo('small', null, String(d.sub))); cuerpo.appendChild(tx);
    var ch = nodo('div', 'chips');
    (d.chips || []).forEach(function (c) { ch.appendChild(boton('chip' + (c[2] ? ' p' : ''), c[0], c[1])); });
    if (ch.firstChild) cuerpo.appendChild(ch);
    cuerpo.appendChild(boton('wsm-cx', '×', function () { cerrarToque(); }));
    T.textContent = ''; T.appendChild(cuerpo);
    if (vieja) cruzarToque(T, vieja, anchoVieja);
    if (T._sale) T._sale();
    if (!ya) { T.hidden = false; entra(T); }
    S.toqueMs = +d.ms || 15000;
    T.onmouseenter = function () { clearTimeout(S.relojToque); };
    T.onmouseleave = function () { dormirToque(); };
    dormirToque();
  }
  /* lo de antes se desvanece encima, pegado a la orilla de donde sale el globito (la del nido), y lo nuevo ya está
     debajo (una sola animación: la de la copia). Si cambia un poco de tamaño, nada se mueve. Antes la copia se borraba
     al cambiar el contenido y el cambio era seco. */
  function cruzarToque(T, vieja, ancho) {
    try {
      if (!vieja.animate || WSM.quieto()) return;
      var lado = (s() && s().lado) || { h: 'der', v: 'abajo' };
      vieja.classList.add('wsm-fantasma');
      vieja.style.width = ancho + 'px';
      vieja.style[lado.h === 'izq' ? 'left' : 'right'] = '0px';
      vieja.style[lado.v === 'arriba' ? 'top' : 'bottom'] = '0px';
      vieja.style.pointerEvents = 'none';
      T.appendChild(vieja);
      var a = vieja.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 180, easing: 'ease-out', fill: 'forwards' });
      a.onfinish = function () { vieja.remove(); };
    } catch (e) { }
  }
  function dormirToque() { clearTimeout(S.relojToque); S.relojToque = setTimeout(cerrarToque, S.toqueMs || 15000); }
  /* el de un encargo: «Eco terminó · Comparativo_v1.xlsx» [Ver] */
  function tocar(agente, e) {
    var arch = (e.archivos || [])[0], necesita = e.estado === 'necesita';
    toque({ clave: 'encargo:' + e.id, agente: agente, tipo: necesita ? 'necesita' : 'termino',
      titulo: nombre(agente) + (necesita ? ' te necesita' : ' terminó'),
      sub: necesita ? (e.titulo || '') : arch ? base(arch.ruta) : (e.titulo || ''),
      chips: [['Ver', function () { ver(agente, e.id); }, true]] });
  }
  /* sin clave: el que esté; con clave: solo si el que está es ese (lo de otro no se cierra) */
  function cerrarToque(clave) {
    if (clave && (!S.toque || S.toque.clave !== clave)) return;
    if (S.toqueSig) { S.toqueSig = null; S.toque = null; return; }      /* ya va saliendo: que no entre el siguiente */
    clearTimeout(S.relojToque);
    var T = R.toque; if (!T || T.hidden) return;
    S.toque = null;
    quitar(T, 240, function () { T.hidden = true; T.textContent = ''; });
  }
  /* [Ver]: el agente, su encargo en la burbuja (ya visto) */
  function ver(agente, id) {
    cerrarToque();
    /* el chat grande está en su ventana: se ve allá (la app lo trae al frente y le pasa cuál) */
    if (s().fuera) { host({ op: 'grande', abierto: true, ver: [agente, id] }); return; }
    if (S.grande.abierto && S.grande.col) { S.grande.col = false; pintarGrande(); }      /* se ve en la plática */
    var g = WSM.piezas().globo, otro = s().elegido !== agente;
    function mostrar() {
      seguir(id);
      try { if (s().elegido !== agente) WSM.elegir(agente, true); } catch (e) { }
      var e = encargo(agente, id);
      if (e && e.estado === 'listo') visto(agente, id);
      abrirGlobo();
    }
    /* de otro agente con la burbuja abierta: la de antes sale entera y luego entra la suya (sin cambiar su contenido
       de golpe a medio camino); lo que te pide algo no se esconde (cerrarGlobo lo deja) */
    if (otro && g && !g.hidden && !S.grande.abierto && !(s().permiso || s().pregunta)) {
      try { WSM.cerrarGlobo(true); } catch (e) { }
      setTimeout(mostrar, WSM.quieto() ? 0 : 280);
    } else mostrar();
  }
  function abrirGlobo() { try { WSM.pintarGlobo(); } catch (e) { } acomodar(pintarEncs); alFondo(); }
  /* lo que te pide algo (sus botones) queda a la vista aunque la burbuja tenga que recorrerse */
  function alFondo() {
    setTimeout(function () {
      try {
        var p = WSM.piezas();
        [p.conv, p.globo].forEach(function (g) { if (g && g.scrollHeight > g.clientHeight) g.scrollTop = g.scrollHeight; });
      } catch (e) { }
    }, 0);
  }
  /* al cerrar la burbuja a mano: dejas de seguir lo que ya terminó (lo que trabaja te toca al terminar) */
  function alCerrar() {
    S.siguiendo = S.siguiendo.filter(function (id) { return !!S.propuestas[id]; });
    S.rancio = true;                          /* sus tarjetas salen con la burbuja; se quitan al volver a pintarla */
  }

  /* ---------- los botones de la barra, según lo que tienes enfrente ---------- */
  var NAVEGADORES = /^(com\.apple\.Safari|com\.google\.Chrome|company\.thebrowser|com\.brave\.Browser|com\.microsoft\.edgemac|org\.mozilla\.firefox|com\.operasoftware|com\.vivaldi|com\.apple\.mail|com\.microsoft\.Outlook)/;
  function frente(c) {
    var t = 'nada';
    if (c && c.seleccion && String(c.seleccion).trim()) t = 'texto';
    else if (c && c.documento) t = 'archivo';
    else if (c && (c.url || NAVEGADORES.test(c.bundle || ''))) t = 'pagina';
    S.frente = { tipo: t, nombre: c && c.documento || '', app: c && c.app || '' };
    pintarBotones();
  }
  function tipoAhora() {
    var adj = ((s() && s().adjuntos) || []).filter(function (x) { return x.ruta; });
    if (adj.length) { S.frente.adjunto = adj[adj.length - 1].ruta; return 'archivo'; }
    S.frente.adjunto = '';
    return S.frente.tipo || 'nada';
  }
  function pintarBotones() {
    if (!R.botones) return;
    var t = tipoAhora(), lista = (S.botones && S.botones[t]) || [], st = s() || {};
    var ver = !!lista.length && !st.responde && !!st.barra && st.conAgentes !== false;
    var k = JSON.stringify([t, lista, ver]);
    if (!S.menuBarra && !R.menuB.hidden && !st.barra) { R.menuB.hidden = true; R.menuB.textContent = ''; }
    if (R.botones._k === k) return;
    R.botones._k = k; R.botones.textContent = ''; R.botones.hidden = !ver;
    if (!ver) { R.menuB.hidden = true; R.menuB.textContent = ''; S.menuBarra = ''; return; }
    lista.forEach(function (b) {
      var e = boton('wsm-bt', b.t + (b.accion === 'entregable' ? ' ▾' : ''), function () { usarBoton(b, e); });
      R.botones.appendChild(e);
    });
  }
  function usarBoton(b, e) {
    var st = s(); if (!st) return;
    if (b.accion === 'panel') { abrirGrande(b.panel); return; }
    if (b.accion === 'pasar') { S.menuBarra = S.menuBarra === 'pasar' ? '' : 'pasar'; if (S.menuBarra) elegirAgente(null, true); else acomodar(function () { R.menuB.hidden = true; R.menuB.textContent = ''; }); return; }
    if (b.accion === 'entregable') { menuPlantillas(); return; }
    /* monito: se lo pide al monito (lo libre basta). Con archivo enfrente, primero su copia a su carpeta. */
    if (b.con_archivo && tipoAhora() === 'archivo' && !S.frente.adjunto) {
      S.pendiente = b.pide;
      host({ op: 'frente_adjuntar', agente: st.elegido });
      return;
    }
    try { WSM.decir(b.pide); } catch (x) { }
  }
  function menuPlantillas() {
    S.menuBarra = S.menuBarra === 'plantillas' ? '' : 'plantillas';
    acomodar(function () {
      R.menuB.textContent = ''; R.menuB.hidden = !S.menuBarra;
      if (!S.menuBarra) return;
      (S.plantillas || []).forEach(function (p) {
        var i = boton('wsm-item', null, function () { proponerPlantilla(p); });
        i.appendChild(nodo('span', null, p.t)); i.appendChild(nodo('small', null, p.d));
        R.menuB.appendChild(i);
      });
      entra(R.menuB);
    });
  }
  function proponerPlantilla(p) {
    var st = s(), ta = WSM.piezas().ta, escrito = ta ? String(ta.value || '').trim() : '';
    var nom = S.frente.nombre || (S.frente.adjunto ? base(S.frente.adjunto) : '');
    var pedido = escrito ? escrito + ' (' + p.t + ')' : nom ? p.t + ' de ' + nom : '';
    if (!pedido) {
      acomodar(function () { R.menuB.textContent = ''; R.menuB.appendChild(nodo('small', 'wsm-vacio', 'Escribe de qué es y vuelve a elegir «' + p.t + '».')); });
      try { ta.focus(); } catch (e) { }
      return;
    }
    var op = { op: 'encargo_proponer', agente: st.elegido, plantilla: p.id, pedido: pedido };
    if (S.frente.adjunto) op.archivo = S.frente.adjunto;
    host(op);
    if (ta) { ta.value = ''; }
    S.menuBarra = '';
    try { WSM.barra(false); } catch (e) { }       /* el menú sale con la barra; se limpia la próxima vez que abra */
  }
  /* la copia del archivo de enfrente llegó a su carpeta: su pedido sale ya */
  function adjuntando(d) { S.subiendo = d && d.nombre; }
  function alAdjunto(ev) {
    if (!S.pendiente || !ev.ruta) return;
    var p = S.pendiente; S.pendiente = null;
    setTimeout(function () { try { WSM.decir(p); } catch (e) { } }, 0);
  }

  /* ---------- el chat grande (⤢): el MISMO chat, en grande ----------
     Ronda 2 · bloque G. No es un segundo chat: la plática y la caja de escribir de la burbuja se acomodan aquí adentro
     (WSM.grande), con la tira de agentes a la izquierda y, a la derecha, «Te esperan» y «Entregas».
       · G-1 (aquí mismo, junto al nido): cuando la app es de antes o en el boceto.
       · G-2 (su propia ventana, que cambia de tamaño y recuerda dónde la dejaste): la app carga esta misma página con
         la clase wsm-ventana; ahí este bloque llena la ventana y la burbuja chica (en la otra página) se calla.
     No se cierra solo: lo nuevo aparece adentro. Dos botones distintos, con su letrero:
       · «─ Minimizar» (y Esc, ⌥ Espacio, un clic en tu Compañero): TODO se guarda; al llamarlo vuelve EN GRANDE.
       · «⤡ Chico»: no guarda nada, el mismo chat sigue abierto en la burbuja chica. */
  function enVentana() { try { return WSM.enVentana(); } catch (e) { return false; } }
  function dibujo(d) {
    try {
      var NS = 'http://www.w3.org/2000/svg', v = document.createElementNS(NS, 'svg'), p = document.createElementNS(NS, 'path');
      v.setAttribute('viewBox', '0 0 16 16'); v.setAttribute('width', '16'); v.setAttribute('height', '16');
      p.setAttribute('d', d); p.setAttribute('fill', 'none'); p.setAttribute('stroke', 'currentColor');
      p.setAttribute('stroke-width', '1.5'); p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round');
      v.appendChild(p); return v;
    } catch (e) { return nodo('i', 'dib'); }
  }
  var DIB = { lupa: 'M10.6 10.6 L14 14 M11.6 7.1 A4.5 4.5 0 1 1 2.6 7.1 A4.5 4.5 0 0 1 11.6 7.1',
    menos: 'M3 8 H13', chico: 'M9.5 6.5 L14 2 M9.5 2.8 V6.5 H13.2 M6.5 9.5 L2 14 M6.5 13.2 V9.5 H2.8',
    arriba: 'M4 10 L8 6 L12 10', abajo: 'M4 6 L8 10 L12 6', equis: 'M4 4 L12 12 M12 4 L4 12', copia: 'M5.5 5.5 V3 H13 V10.5 H10.5 M3 5.5 H10.5 V13 H3 Z' };
  function icoBoton(c, d, titulo, fn) { var b = boton(c, null, fn); b.appendChild(dibujo(DIB[d])); b.title = titulo; return b; }

  function abrirGrande(ver) {
    if (ver === 'entregas' || ver === 'encargos') S.grande.col = true;      /* «Mis entregas»: con su columna a la vista */
    var fuera = false; try { fuera = !!s().fuera; } catch (e) { }
    if (fuera) { host({ op: 'grande', abierto: true }); return; }           /* ya está en su ventana: que venga al frente */
    if (S.grande.abierto) { if (S.grande.listo) pintarGrande(); return; }
    S.grande.abierto = true; S.grande.listo = false;
    pedirDatos();
    if (enApp() && !enVentana()) host({ op: 'grande', abierto: true }); else grandeListo(true);
  }
  /* la app contesta: «ya creció el panel» (una app de antes: el grande va aquí, junto al nido) */
  function grandeListo(si) {
    if (!si || !S.grande.abierto) return;
    S.grande.listo = true;
    var G = R.grande;
    if (G._sale) G._sale();
    armarGrande();
    try { WSM.modo('grande'); } catch (e) { }
    if (G.hidden) acomodar(function () { G.hidden = false; });
    try { WSM.grande(true, R.gCentro); } catch (e) { }
    pintarGrande();
  }
  /* la app contesta: «el grande está en SU ventana» (si) o «esa ventana se guardó» (como: 'grande' minimizado, 'chico') */
  function grandeFuera(si, como) {
    S.grande.abierto = false; S.grande.listo = false;
    try { WSM.fuera(!!si, como); } catch (e) { }
    /* (si quedó en chico, la app abre la barra enseguida: toma lo que tienes enfrente y le da el teclado) */
  }
  /* «─»: todo se guarda en el monito; al volver a llamarlo abre en grande, donde lo dejaste (G3-a) */
  function minimizar() { cerrarGrande('grande'); }
  /* «⤡»: de vuelta a la burbuja chica */
  function achicar() { cerrarGrande('chico'); }
  function cerrarGrande(como) {
    if (!S.grande.abierto) return;
    var chico = como === 'chico';
    try { WSM.modo(chico ? 'chico' : 'grande'); } catch (e) { }
    if (enVentana()) { host({ op: 'grande', abierto: false, como: chico ? 'chico' : 'grande' }); return; }   /* la app guarda la ventana */
    S.grande.abierto = false;
    var G = R.grande;
    buscarCerrar();
    montarFichas(false);
    try { WSM.grande(false); } catch (e) { }
    quitar(G, 260, function () { G.hidden = true; if (enApp() && !S.grande.abierto) host({ op: 'grande', abierto: false }); });
    if (chico) setTimeout(function () { try { WSM.barra(true); } catch (e) { } }, 0);
  }
  function pedirDatos() {
    var a = s() && s().elegido; if (!a) return;
    host({ op: 'historial', agente: a });
    host({ op: 'entregas', agente: a });
  }
  function alElegir() { if (S.grande.abierto) { pedirDatos(); pintarGrande(); } }
  /* las filas de Entregas también se arrastran y tienen miniatura: la app las conoce por su ruta */
  function pedirTodas(agente, lista) {
    S.filas = S.filas || {};
    lista.slice(0, 12).forEach(function (x) {
      var k = clave(agente, x.ruta);
      if (!S.filas[k]) { S.filas[k] = { agente: agente, ruta: x.ruta }; if (!S.cartas[k]) host({ op: 'entrega', agente: agente, ruta: x.ruta }); }
    });
  }
  /* la armazón, una vez: tira · (encabezado, buscar, la plática y la caja) · columna */
  function armarGrande() {
    var G = R.grande; if (!G || R.gCentro) return;
    R.gTira = nodo('div', 'tira'); R.gCentro = nodo('div', 'centro'); R.gCol = nodo('div', 'col');
    R.gCab = nodo('div', 'gcab'); R.gBusca = nodo('div', 'gbusca'); R.gBusca.hidden = true;
    R.gNombre = nodo('b', 'nom'); R.gEstado = nodo('i', 'est'); R.gAsa = nodo('div', 'asa');
    R.gVerCol = boton('gcol', null, function () { S.grande.col = !S.grande.col; pintarGrande(); });
    var copiar = icoBoton('gb', 'copia', 'Copiar toda la plática', function (b) {
      var t = ''; try { t = WSM.copiarTodo(); } catch (e) { }
      b.classList.add(t ? 'hecho' : 'nada'); setTimeout(function () { b.classList.remove('hecho', 'nada'); }, 1400);
    });
    copiar.appendChild(nodo('span', null, 'Copiar todo'));
    var lupa = icoBoton('gb', 'lupa', 'Buscar en la plática  (⌘F)', function () { if (R.gBusca.hidden) buscarAbrir(); else buscarCerrar(); });
    /* cambiar de tamaño y guardar son DOS cosas: cada una con su botón y su letrero; «Minimizar», el último (la esquina) */
    var chico = icoBoton('gb gchico', 'chico', 'Chico: el mismo chat en la burbuja, junto a tu Compañero', function () { achicar(); });
    chico.appendChild(nodo('span', 'let', 'Chico'));
    var menos = icoBoton('gb gmin', 'menos', 'Minimizar: todo se guarda en tu Compañero y vuelve igual con ⌥ Espacio o un clic en él  (Esc)', function () { minimizar(); });
    menos.appendChild(nodo('span', 'let', 'Minimizar'));
    [R.gNombre, R.gEstado, R.gAsa, copiar, R.gVerCol, lupa, chico, menos].forEach(function (n) { R.gCab.appendChild(n); });
    /* buscar: lo que escribes marca los mensajes que lo dicen; Enter o las flechas saltan entre ellos */
    R.gQ = nodo('input'); R.gQ.type = 'text'; R.gQ.placeholder = 'Buscar en esta plática…'; R.gQ.spellcheck = false;
    R.gCuenta = nodo('small', 'cuenta');
    function ir(d) { var r = { n: 0, i: 0 }; try { r = WSM.irHallado(d); } catch (e) { } cuentaBusca(r); }
    R.gQ.addEventListener('input', function () { var r = { n: 0, i: 0 }; try { r = WSM.buscar(R.gQ.value); } catch (e) { } cuentaBusca(r); });
    R.gQ.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); ir(e.shiftKey ? 1 : -1); }
      else if (e.key === 'Escape') { e.preventDefault(); if (e.stopPropagation) e.stopPropagation(); buscarCerrar(); }
    });
    [R.gQ, R.gCuenta, icoBoton('gb', 'arriba', 'El anterior', function () { ir(-1); }), icoBoton('gb', 'abajo', 'El siguiente', function () { ir(1); }),
      icoBoton('gb', 'equis', 'Cerrar la búsqueda', function () { buscarCerrar(); })].forEach(function (n) { R.gBusca.appendChild(n); });
    R.gCentro.appendChild(R.gCab); R.gCentro.appendChild(R.gBusca);
    /* la columna: lo que te espera (las fichas del carril 2 se montan en R.gFichas), tus entregas y los encargos */
    R.gEsperan = nodo('div', 'sec esperan'); R.gFichas = nodo('div', 'fichas'); R.gEnts = nodo('div', 'sec'); R.gEncs = nodo('div', 'sec');
    R.gPie = nodo('div', 'pie');
    R.gPie.appendChild(boton('wsm-ir', 'Editar los botones de la barra', function () { host({ op: 'botones_editar' }); }));
    R.gPie.appendChild(boton('wsm-ir', 'Seguir en la página', function () { host({ op: 'seguir', agente: s().elegido }); }));
    [R.gEsperan, R.gEnts, R.gEncs, R.gPie].forEach(function (n) { R.gCol.appendChild(n); });
    [R.gTira, R.gCentro, R.gCol].forEach(function (n) { G.appendChild(n); });
    try {
      document.addEventListener('keydown', function (e) {
        if (!S.grande.abierto || !S.grande.listo) return;
        if ((e.metaKey || e.ctrlKey) && (e.key === 'f' || e.key === 'F')) { e.preventDefault(); buscarAbrir(); }
      });
      window.addEventListener('resize', function () { if (S.grande.abierto) pintarGrande(); });
    } catch (e) { }
  }
  function cuentaBusca(r) { if (R.gCuenta) R.gCuenta.textContent = !R.gQ.value.trim() ? '' : r.n ? r.i + ' de ' + r.n : 'Sin resultados'; }
  function buscarAbrir() { if (!R.gBusca) return; R.gBusca.hidden = false; if (R.gQ.focus) R.gQ.focus(); if (R.gQ.select) R.gQ.select(); }
  function buscarCerrar() {
    if (!R.gBusca || R.gBusca.hidden) return;
    R.gBusca.hidden = true; R.gQ.value = ''; R.gCuenta.textContent = '';
    try { WSM.buscar(''); WSM.mic.enfocar(); } catch (e) { }
  }
  /* su estado («pensando», «trabajando»…) junto a su nombre: lo dice la burbuja (pintarCab) */
  function estadoGrande(t, vivo) {
    if (!R.gEstado) return;
    if (R.gEstado.textContent !== (t || '')) R.gEstado.textContent = t || '';
    R.gEstado.className = 'est' + (vivo ? ' vivo' : '');
  }
  /* ---------- «Te esperan»: lo que necesita tu clic, de TODOS los agentes ----------
     Dos cosas, juntas:
       · las FICHAS de la bandeja (carril 2 · CONTRATO_BANDEJA.md): si su espejo está cargado (WSFichas), él mismo las
         pinta en R.gFichas (WSFichas.pintar) y las repinta cuando cambian; aquí solo se cuentan (para el título y el
         número de cada agente en la tira). Sus botones no deciden nada: se lo piden a la app.
       · lo que la burbuja ya sabía: los encargos que te necesitan o que terminaron sin que los vieras ([Ver]).
     Sin el espejo de las fichas (una app de antes), las tarjetas de OK que esperan junto al monito salen como un
     renglón que lo dice. */
  function fichas() { try { return typeof WSFichas !== 'undefined' && WSFichas && typeof WSFichas.pintar === 'function' ? WSFichas : null; } catch (e) { return null; } }
  /* cuántas fichas esperan tu clic (de un agente, o de todos con null) */
  function fichasDe(agente) {
    var F = fichas(); if (!F || typeof F.lista !== 'function') return 0;
    try { return (F.lista() || []).filter(function (f) { return f && f.estado !== 'hecha' && (agente == null || f.agente === agente); }).length; } catch (e) { return 0; }
  }
  function montarFichas(si) {
    var F = fichas(); if (!F || !R.gFichas) return;
    try {
      if (si && !S.fichasEn) {
        S.fichasEn = true; F.pintar(R.gFichas, { mini: true });
        if (!S.fichasOyen && typeof F.alCambiar === 'function') { S.fichasOyen = true; F.alCambiar(function () { if (S.grande.abierto) pintarGrande(); }); }
      } else if (!si && S.fichasEn) { S.fichasEn = false; if (typeof F.soltar === 'function') F.soltar(R.gFichas); }
    } catch (e) { }
  }
  function esperan() {
    var l = [], v = S.vistoLocal || {};
    for (var a0 in S.encargos) (S.encargos[a0] || []).forEach(function (e) {
      var necesita = e.estado === 'necesita', a = e.agente_ || a0;
      if (!necesita && !(e.estado === 'listo' && !e.visto && !v[e.id])) return;
      var arch = (e.archivos || [])[0];
      l.push({ id: 'e:' + e.id, agente: a, titulo: nombre(a) + (necesita ? ' te necesita' : ' terminó'), tono: necesita ? 'pide' : '',
        sub: necesita ? (e.titulo || e.pedido || '') : arch ? base(arch.ruta) : (e.titulo || ''),
        botones: [['Ver', function () { ver(a, e.id); }, true]] });
    });
    var sueltas = 0; for (var k in (S.esperan || {})) if (S.esperan[k]) sueltas++;
    if (sueltas && !fichas())
      l.push({ id: 'ok', agente: '', titulo: sueltas > 1 ? sueltas + ' tarjetas esperan tu OK' : 'Una tarjeta espera tu OK', sub: 'Está junto a tu Compañero.', tono: 'pide', botones: [] });
    return l;
  }
  /* cuántas cosas te esperan de un agente (el número de su monito en la tira) */
  function esperanDe(agente, lista) { return (lista || esperan()).filter(function (x) { return x.agente === agente; }).length + fichasDe(agente); }
  function sitioFichas() { armarGrande(); return R.gFichas || null; }

  function pintarGrande() {
    var G = R.grande; if (!G || !S.grande.abierto || !S.grande.listo || !R.gCentro) return;
    var a = (s() && ag(s().elegido)) || { n: '', c: '#fff', f: 'bolita', id: '' };
    var agentes = (s() && s().agentes) || [], pend = esperan(), nFichas = fichasDe(null), total = pend.length + nFichas;
    montarFichas(true);
    var todos = []; for (var x in S.encargos) todos = todos.concat(S.encargos[x] || []);
    var ents = S.lista[a.id] || [];
    /* angosto (junto al nido): la columna se abre con su botón, encima de la plática; ancho (su ventana): siempre */
    var ancho = +G.offsetWidth || 0, angosto = ancho < 700;
    G.classList.toggle('angosto', angosto); G.classList.toggle('ver-col', !!S.grande.col && angosto);
    G.classList.toggle('una', agentes.length < 2);
    /* la tira: tus agentes con su monito y, si tienen algo pendiente, su número */
    var tk = JSON.stringify([agentes.map(function (g) { return [g.id, g.n, g.c, g.f, esperanDe(g.id, pend)]; }), a.id]);
    if (R.gTira._k !== tk) {
      R.gTira._k = tk; R.gTira.textContent = '';
      agentes.forEach(function (g) {
        var n = esperanDe(g.id, pend);
        var b = boton('ag' + (g.id === a.id ? ' on' : ''), null, function () { try { WSM.elegir(g.id, true); WSM.mic.enfocar(); } catch (e) { } });
        b.style.setProperty('--c', g.c); b.title = g.n + (n ? ' · ' + n + (n > 1 ? ' cosas te esperan' : ' cosa te espera') : '');
        try { b.appendChild(monito(g.c, g.f, 34, { quieto: g.id !== a.id })); } catch (e) { }
        b.appendChild(nodo('span', null, g.n));
        if (n) b.appendChild(nodo('b', 'n', n > 9 ? '9+' : String(n)));
        R.gTira.appendChild(b);
      });
    }
    if (R.gNombre.textContent !== (a.n || 'Workspace')) R.gNombre.textContent = a.n || 'Workspace';
    G.style.setProperty('--c', a.c);
    var vk = total + '|' + !!S.grande.col;
    if (R.gVerCol._k !== vk) {
      R.gVerCol._k = vk; R.gVerCol.textContent = '';
      R.gVerCol.appendChild(nodo('span', null, S.grande.col ? 'Volver a la plática' : total ? 'Te esperan' : 'Entregas'));
      if (total && !S.grande.col) R.gVerCol.appendChild(nodo('b', 'n', total > 9 ? '9+' : String(total)));
      R.gVerCol.className = 'gcol' + (total ? ' hay' : '');
    }
    /* «Te esperan (n)»: arriba las fichas (las pinta su espejo), luego lo de los encargos */
    var ek = nFichas + '|' + JSON.stringify(pend.map(function (p) { return [p.id, p.titulo, p.sub, p.botones.map(function (b) { return b[0]; })]; }));
    if (R.gEsperan._k !== ek) {
      R.gEsperan._k = ek; R.gEsperan.textContent = '';
      var h = nodo('div', 'tit', 'Te esperan'); if (total) h.appendChild(nodo('b', 'n', String(total))); R.gEsperan.appendChild(h);
      R.gEsperan.appendChild(R.gFichas);
      if (!total) R.gEsperan.appendChild(nodo('small', 'wsm-vacio', 'Nada te espera. Aquí sale lo que necesite tu clic.'));
      pend.forEach(function (p) {
        var f = nodo('div', 'espera' + (p.tono ? ' ' + p.tono : '')), ac = ag(p.agente) || { c: '#b9a3ff' };
        var pt = nodo('i', 'pt'); pt.style.setProperty('--c', ac.c); f.appendChild(pt);
        var tx = nodo('div', 'tx'); tx.appendChild(nodo('b', null, p.titulo)); if (p.sub) tx.appendChild(nodo('small', null, p.sub)); f.appendChild(tx);
        var ch = nodo('div', 'chips');
        p.botones.forEach(function (b) { ch.appendChild(boton('chip' + (b[2] ? ' p' : ''), b[0], function () { if (typeof b[1] === 'function') b[1](); })); });
        if (ch.firstChild) f.appendChild(ch);
        R.gEsperan.appendChild(f);
      });
    }
    /* «Entregas» (las de su carpeta) */
    var nk = a.id + '|' + JSON.stringify([ents, imgs(a.id, ents)]);
    if (R.gEnts._k !== nk) {
      R.gEnts._k = nk; R.gEnts.textContent = '';
      R.gEnts.appendChild(nodo('div', 'tit', 'Entregas'));
      if (!ents.length) R.gEnts.appendChild(nodo('small', 'wsm-vacio', 'Todavía no hay entregas en su carpeta.'));
      ents.slice(0, 12).forEach(function (e) { R.gEnts.appendChild(fila(a.id, e)); });
    }
    /* «Encargos» (de todos): en curso y terminados */
    var ck = JSON.stringify(todos);
    if (R.gEncs._k !== ck) {
      R.gEncs._k = ck; R.gEncs.textContent = ''; R.gEncs.hidden = !todos.length;
      var curso = todos.filter(function (e) { return e.estado !== 'listo' && e.estado !== 'parado'; }), fin = todos.filter(function (e) { return e.estado === 'listo' || e.estado === 'parado'; });
      [['Encargos en curso', curso], ['Encargos terminados', fin.slice(0, 6)]].forEach(function (g) {
        if (!g[1].length) return;
        R.gEncs.appendChild(nodo('div', 'tit', g[0]));
        g[1].forEach(function (e) {
          var f = nodo('div', 'fila enc'), ac = ag(e.agente_) || { c: '#fff' };
          var pt = nodo('i', 'pt'); pt.style.setProperty('--c', ac.c); f.appendChild(pt);
          var tx = nodo('div', 'tx'); tx.appendChild(nodo('b', null, e.titulo || e.pedido || ''));
          var p = e.pasos, sub = nombre(e.agente_) + ' · ' + (e.estado === 'trabajando' && p ? 'paso ' + Math.min(p.i + 1, p.n) + ' de ' + p.n : e.estado === 'listo' ? 'terminó ' + hace(e.terminado || e.creado) : ESTADO_TXT[e.estado] || e.estado);
          tx.appendChild(nodo('small', null, sub)); f.appendChild(tx);
          f.appendChild(boton('chip' + (e.estado === 'listo' && !e.visto || e.estado === 'necesita' ? ' p' : ''), 'Ver', function () { ver(e.agente_, e.id); }));
          R.gEncs.appendChild(f);
        });
      });
    }
    asa();
  }
  /* de dónde se toma la ventana para moverla (su encabezado, donde no hay botones): se lo dice a la app */
  function asa() {
    if (!enVentana() || !R.gAsa) return;
    var r = rect(R.gAsa), t = R.gTira ? rect(R.gTira) : [0, 0, 0, 0];
    var z = [r, [t[0], t[1], t[2], 14]].filter(function (q) { return q[2] > 8 && q[3] > 4; }), k = JSON.stringify(z);
    if (k === S.asaK) return;
    S.asaK = k; host({ op: 'grande_asa', zonas: z });
  }
  function vivo() { var t = s() && s().turno; if (!t || !(t.vivo || t.texto)) return null; return { rol: 'agente', texto: t.texto || '', vivo: !!t.vivo, archivos: t.archivos }; }
  function imgs(a, ents) { return ents.map(function (x) { var f = S.filas && S.filas[clave(a, x.ruta)]; return f && f.img ? 1 : 0; }); }
  function fila(a, x) {
    var f = nodo('div', 'fila'), e = x.ext || ext(x.ruta), fl = S.filas && S.filas[clave(a, x.ruta)];
    var arr = nodo('div', 'wsm-ent-arr'); arr._ent = { agente: a, ruta: x.ruta };
    var ic = nodo('div', 'wsm-ent-mini chica'); ic.style.setProperty('--e', COLOR_EXT[e] || '#6b6b78');
    if (fl && fl.img) { var im = nodo('img'); im.src = fl.img; im.draggable = false; ic.appendChild(im); } else ic.appendChild(nodo('b', 'ext', (e || '?').toUpperCase().slice(0, 4)));
    arr.appendChild(ic);
    var tx = nodo('div', 'tx'); tx.appendChild(nodo('b', null, x.nombre || base(x.ruta)));
    tx.appendChild(nodo('small', null, [(e || '').toUpperCase(), hace(x.t), x.version ? 'v' + x.version : ''].filter(Boolean).join(' · ')));
    arr.appendChild(tx); f.appendChild(arr);
    f.appendChild(boton('chip', 'Vista rápida', function () { pedir(null, 'vista', { op: 'entrega_vista', agente: a, ruta: x.ruta }); }));
    f.appendChild(boton('chip p', 'Abrir', function () { pedir(null, 'abierto', { op: 'entrega_abrir', agente: a, ruta: x.ruta, modo: 'abrir' }); }));
    return f;
  }

  /* ---------- las zonas de arrastre para la app (cada vez que cambian) ---------- */
  function zonasArrastre() {
    if (!enApp() || !R.w || !R.w.raiz) return;
    var z = [];
    for (var k in S.cartas) {
      var c = S.cartas[k];
      if (c.arr && c.arr.offsetParent && !c.arr.hidden && c.info) { var r = rect(c.arr); if (r[2] && r[3]) z.push(r.concat([c.agente, cual(c)])); }
    }
    if (S.grande.abierto && R.gCol) {
      var todosN = []; (function rec(n) { [].slice.call(n.children || []).forEach(function (h) { if (h._ent) todosN.push(h); else rec(h); }); })(R.gCol);
      todosN.forEach(function (n) { var r = rect(n); if (r[2] && r[3] && n.offsetParent) z.push(r.concat([n._ent.agente, n._ent.ruta])); });
    }
    var key = JSON.stringify(z);
    if (key === S.zonasK) return;
    S.zonasK = key;
    host({ op: 'zonas_arrastre', zonas: z });
  }
  function arrastrando(si, soltado) {
    if (R.w && R.w.raiz) R.w.raiz.classList.toggle('sacando', !!si);
    if (!si && soltado) hecho({ que: 'soltado' });
  }
  /* Un clic que la app (o el puente) tiene que hacer: sale, y su resultado se dice en la tarjeta. Si en la app no llega
     respuesta, se dice también (antes, con la app de antes, los botones no hacían nada y nadie lo decía). */
  function pedir(c, que, op) {
    host(op);
    if (c) { c.espera = que; }
    if (!enApp()) return;
    clearTimeout(S.relojHecho);
    S.esperaHecho = { que: que, agente: op.agente, ruta: op.ruta };
    S.relojHecho = setTimeout(function () {
      var e = S.esperaHecho; if (!e) return;
      S.esperaHecho = null;
      hecho({ que: 'sin_respuesta', ok: false, agente: e.agente, ruta: e.ruta });
    }, ESPERA_HECHO_MS);
  }
  /* lo que pasó con tu clic, en una línea chica que se va sola: en la tarjeta de esa entrega si la hay (debajo de sus
     botones), si no en la burbuja (o en el pie del panel grande). Nunca tapa la respuesta. */
  function hecho(d) {
    d = d || {};
    var que = String(d.que || ''), ok = d.ok !== false && !/^(no_|sin_)/.test(que);
    if (S.esperaHecho && (!d.ruta || d.ruta === S.esperaHecho.ruta || que === 'sin_respuesta')) { S.esperaHecho = null; clearTimeout(S.relojHecho); }
    if (que === 'guardar_cancelado') return;
    var txt = ok ? HECHO_TXT[que] : (NO_TXT[que] || NO_TXT['no_' + que] || '');
    if (ok && que === 'abierto' && d.app) txt = 'Listo, lo abrí en ' + String(d.app).slice(0, 40) + '.';
    if (ok && que === 'revelado' && d.ejecutable) txt = 'Es un programa: te lo enseñé en Finder en vez de abrirlo.';
    if (!ok && d.texto) txt = String(d.texto).slice(0, 200);
    if (!txt) return;
    if (d.ensayo) txt += ' (ensayo)';
    if (que === 'sin_ruta' && d.agente && d.ruta) host({ op: 'entrega', agente: d.agente, ruta: d.ruta });   /* que la prepare */
    var c = d.agente && d.ruta ? S.cartas[clave(d.agente, d.ruta)] : null;
    if (!c && d.agente && d.ruta) for (var k in S.cartas) { var x = S.cartas[k]; if (x.agente === d.agente && cual(x) === d.ruta) { c = x; break; } }
    var donde = c && c.n && c.n.parentNode ? c.n : S.grande.abierto && R.gPie ? R.gPie : R.w && R.w.globo;
    if (!donde || donde.hidden) return;
    var viejo = R.hecho; R.hecho = null;
    acomodar(function () {
      if (viejo && viejo.parentNode) viejo.remove();
      var h = R.hecho = nodo('small', 'wsm-hecho-t' + (ok ? '' : ' mal'), txt);
      if (donde === (c && c.n) && c.cambios && donde.insertBefore) donde.insertBefore(h, c.cambios);
      else if (donde === R.gPie || !R.w.uso || !donde.insertBefore) donde.appendChild(h); else donde.insertBefore(h, R.w.uso);
      entra(h);
    });
    setTimeout(function () { var h = R.hecho; if (h && h.parentNode) quitar(h, 200, function () { h.remove(); }); }, ok ? 2600 : 5200);
  }
  /* «Pedir cambios» con tus palabras (tu respuesta en la barra, cuando lo último fue una entrega): la misma tarjeta
     dice «Haciendo la v2 · «…»». → true si salió. */
  function pedirCambioDe(agente, ruta, texto) {
    var c = S.cartas[clave(agente, ruta)];
    if (!c) for (var k in S.cartas) { var x = S.cartas[k]; if (x.agente === agente && cual(x) === ruta) { c = x; break; } }
    if (!c || !String(texto || '').trim()) return false;
    pedirCambio(c, String(texto).trim().slice(0, 1000));
    return true;
  }
  /* que la tarjeta que está cambiando quede a la vista */
  function seguirCambio(agente) {
    for (var k in S.cartas) { var c = S.cartas[k]; if (c.agente === agente && c.cambio && c.n && c.n.parentNode) { aLaVistaN(c.hace); return; } }
  }
  /* ¿esa entrega la hizo su conversación de trabajo (un encargo o un «Pedir cambios»)? Entonces tu respuesta a ella va,
     de entrada, como «Pedir cambios» a esa conversación; una que salió de la plática del monito sigue la plática. */
  function deEncargo(agente, ruta) {
    var c = S.cartas[clave(agente, ruta)];
    if (c && c.deEncargo) return true;
    return (S.encargos[agente] || []).some(function (e) {
      return e.destino === ruta || (e.archivos || []).some(function (a) { return a.ruta === ruta; });
    });
  }
  /* la entrega del último encargo terminado que ves en la burbuja (de ese agente), o null */
  function entregaVisible(agente) {
    var ids = visibles();
    for (var i = ids.length - 1; i >= 0; i--) {
      var e = buscar(ids[i]);
      if (e && e.agente_ === agente && e.estado === 'listo' && (e.archivos || []).length) {
        var a = e.archivos[e.archivos.length - 1], c = S.cartas[clave(agente, a.ruta)];
        return { ruta: (c && cual(c)) || a.ruta, titulo: a.titulo || e.titulo || '' };
      }
    }
    return null;
  }
  /* ¿un encargo de ese agente trabaja en segundo plano? (el monito hace su gesto de trabajo) */
  function trabajaEnFondo(agente) {
    return (S.encargos[agente] || []).some(function (e) { return e.estado === 'trabajando'; });
  }

  var W = { montar: montar, piezas: piezas, recibir: recibir, tarjeta: tarjeta, miniatura: miniatura, propuesta: propuesta,
    decidido: decidido, hay: hay, pintar: pintarEncs, alCerrar: alCerrar, frente: frente, botones: pintarBotones,
    alAdjunto: alAdjunto, adjuntando: adjuntando, abrirGrande: abrirGrande, cerrarGrande: cerrarGrande,
    minimizar: minimizar, achicar: achicar, grandeFuera: grandeFuera, estadoGrande: estadoGrande, alElegir: alElegir,
    buscarAbrir: buscarAbrir, buscarCerrar: buscarCerrar, esperan: esperan, esperanDe: esperanDe, sitioFichas: sitioFichas, fichasDe: fichasDe,
    pintarGrande: pintarGrande,
    grandeListo: grandeListo, grandeAbierto: function () { return S.grande.abierto; }, zonas: zonasArrastre,
    arrastrando: arrastrando, hecho: hecho, pendientes: pendientes, s: S, pedirCambioDe: pedirCambioDe,
    seguirCambio: seguirCambio, trabajaEnFondo: trabajaEnFondo, deEncargo: deEncargo, entregaVisible: entregaVisible,
    piezasDentro: piezasDentro,
    toque: toque, gesto: gesto, cerrarToque: cerrarToque, cuenta: cuenta, nombre: nombre };
  M.alHost = null;
  for (var k in W) M[k] = W[k];
  return M;
})();
