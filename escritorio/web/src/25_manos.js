/* ================= las manos en la burbuja (F1: ver y señalar) =================
   Parte de la burbuja (la arma WSM.montar, en su misma caja y con sus mismas zonas de clic), no un añadido aparte:
     · la tarjeta de permiso de la Mac: qué necesita y para qué, en una línea, con el botón que abre el panel exacto de
       Ajustes; espera a que macOS diga que ya y da las gracias;
     · el ojito de «estoy mirando», mientras ve o lee tu ventana (privacidad: nunca mira a escondidas);
     · el nido vacío mientras el monito vuela a señalar (vuela en la capa de la pantalla, escritorio/web/senalar.html).
   Lo que eliges sale por el mismo `host` de la burbuja con op «manos_*»: lo atiende la app, no va al puente.
   Movimiento: cada pieza tiene UN dueño de su animación (su clase); lo que ya se ve no se vuelve a animar. */
var WSMManos = (function () {
  var R = {}, S = { tarjetas: {}, ojo: 0, fuera: null };
  var M = { alHost: null };

  function host(op) {
    if (M.alHost) { try { M.alHost(op); } catch (e) { } return; }
    try { WSM.host(op); } catch (e) { }
  }
  function nodo(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
  function mono() { try { return WSM.mono(); } catch (e) { return null; } }
  /* lo que cambia aquí recorre la burbuja de arriba: que se deslice (el `acomodar` de la burbuja) */
  function acomodar(fn) { try { WSM.acomodar(fn); } catch (e) { fn(); } }
  /* sale deslizándose: deja su hueco al momento y se desvanece en su lugar (el `salir` de la burbuja) */
  function quitar(n, ms, fn) { try { WSM.salir(n, ms, fn); } catch (e) { fn(); } }

  /* `r`: las piezas de la burbuja (WSM.montar): su caja va justo antes del nido */
  function montar(r) {
    R.caja = nodo('div', 'wsmm');
    if (r && r.raiz && r.nido && r.raiz.insertBefore) r.raiz.insertBefore(R.caja, r.nido);
    else if (r && r.raiz) r.raiz.appendChild(R.caja);
    host({ op: 'manos_listo' });
    return R.caja;
  }
  /* lo que se puede tocar (para las zonas de clic de la burbuja) */
  function piezas() { return R.caja ? [].slice.call(R.caja.children || []) : []; }

  /* ---------- la tarjeta de permiso ---------- */
  function icoCandado() {
    if (!document.createElementNS) return nodo('i', 'wsmm-ico');
    var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('viewBox', '0 0 9 9'); s.setAttribute('width', '18'); s.setAttribute('height', '18'); s.setAttribute('class', 'wsmm-ico');
    /* un candadito pixel (9×9): arco y cuerpo */
    [[2, 1, 5, 1], [2, 2, 1, 2], [6, 2, 1, 2], [1, 4, 7, 4]].forEach(function (r) {
      var q = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      q.setAttribute('x', r[0]); q.setAttribute('y', r[1]); q.setAttribute('width', r[2]); q.setAttribute('height', r[3]); s.appendChild(q);
    });
    var o = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    o.setAttribute('x', 4); o.setAttribute('y', 5); o.setAttribute('width', 1); o.setAttribute('height', 2); o.setAttribute('class', 'hueco'); s.appendChild(o);
    return s;
  }
  /* La tarjeta de un permiso de la Mac. Si ya está a la vista (la herramienta lo volvió a pedir), NO vuelve a empezar:
     se queda en el paso en que va (esperando en Ajustes, «no llega»…). Una tarjeta por permiso. */
  function permiso(d) {
    var t = S.tarjetas[d.id];
    if (t && t.estado && t.estado !== 'pide') return;
    if (!t) {
      t = { n: nodo('div', 'wsmm-tarjeta') };
      var cab = nodo('div', 'wsmm-cab'); cab.appendChild(icoCandado()); cab.appendChild(nodo('b', null, 'Permiso de la Mac'));
      var x = nodo('button', 'wsmm-x'); x.title = 'Ahora no'; x.textContent = '×';
      x.onclick = function () { host({ op: 'manos_permiso', accion: 'cerrar', permiso: t.permiso }); };
      cab.appendChild(x);
      t.txt = nodo('p', 'wsmm-txt'); t.nota = nodo('small', 'wsmm-nota'); t.chips = nodo('div', 'chips');
      [cab, t.txt, t.nota, t.chips].forEach(function (k) { t.n.appendChild(k); });
      S.tarjetas[d.id] = t;
      var m = mono(); if (m && !WSM.quieto()) { m.salta(.7); if (m.signo) m.signo('pregunta', { donde: 'der', esc: .8 }); }
    }
    acomodar(function () {
      if (t.n._sale) t.n._sale();                         /* volvió mientras salía: se queda, sin volver a entrar */
      if (!t.n.parentNode) R.caja.insertBefore(t.n, R.caja.firstChild);
      t.n.classList.remove('gracias', 'espera');
      t.permiso = d.permiso; t.estado = 'pide';
      t.txt.textContent = d.texto || '';
      t.nota.textContent = d.nota || '';
      botones(t, [[d.boton || 'Abrir Ajustes', 'abrir', true], ['Ahora no', 'cerrar']]);
    });
  }
  function botones(t, lista) {
    t.chips.textContent = '';
    lista.forEach(function (b) {
      var e = nodo('button', 'chip' + (b[2] ? ' p' : ''), b[0]);
      e.onclick = function () { host({ op: 'manos_permiso', accion: b[1], permiso: t.permiso }); };
      t.chips.appendChild(e);
    });
  }
  function permisoEstado(d) {
    var t = S.tarjetas[d.id]; if (!t) return;
    acomodar(function () { estadoDe(t, d); });
  }
  function estadoDe(t, d) {
    t.estado = d.estado || t.estado;
    t.txt.textContent = d.texto || '';
    t.n.classList.toggle('espera', d.estado === 'espera');
    if (d.botones && d.botones.length) {                   /* la app dice qué se puede hacer (no llega, confirmar…) */
      t.nota.textContent = '';
      botones(t, d.botones.map(function (b) { return [String(b[0]), String(b[1]), !!b[2]]; }));
    } else if (d.estado === 'espera') {
      t.nota.textContent = '';                              /* el texto de la app ya dice que se da cuenta solo */
      botones(t, [['Ya lo prendí', 'ya', true], ['Ahora no', 'cerrar']]);
    } else if (d.estado === 'reiniciar') {
      t.nota.textContent = 'Vuelvo enseguida, en el mismo lugar.';
      botones(t, [['Reabrir Compañero', 'reiniciar', true], ['Ahora no', 'cerrar']]);
    } else if (d.estado === 'reabre') {                    /* se reabre sola: sin botones, solo la línea */
      t.nota.textContent = ''; t.chips.textContent = '';
    } else if (d.estado === 'gracias') {
      /* una sola línea y se va: nunca otra tarjeta para el mismo permiso */
      t.n.classList.add('gracias'); t.nota.textContent = ''; t.chips.textContent = '';
      var m = mono(); if (m && !WSM.quieto()) { m.salta(1.05); if (m.rafaga) m.rafaga(7); }
      setTimeout(function () { cerrar(d.id); }, 2200);
    }
  }
  function cerrar(id) {
    var t = S.tarjetas[id]; if (!t) return;
    delete S.tarjetas[id];
    quitar(t.n, 320, function () { if (!S.tarjetas[id]) t.n.remove(); });
  }

  /* ---------- el ojito: «estoy mirando» ---------- */
  function icoOjo() {
    if (!document.createElementNS) return nodo('i', 'wsmm-ico');
    var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('viewBox', '0 0 11 7'); s.setAttribute('width', '22'); s.setAttribute('height', '14'); s.setAttribute('class', 'wsmm-ojo-svg');
    /* el ojo, pixel: contorno y pupila (la pupila recorre de lado a lado en escalones) */
    [[3, 0, 5, 1], [1, 1, 2, 1], [8, 1, 2, 1], [0, 2, 1, 3], [10, 2, 1, 3], [1, 5, 2, 1], [8, 5, 2, 1], [3, 6, 5, 1]].forEach(function (r) {
      var q = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      q.setAttribute('x', r[0]); q.setAttribute('y', r[1]); q.setAttribute('width', r[2]); q.setAttribute('height', r[3]); s.appendChild(q);
    });
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    p.setAttribute('x', 4); p.setAttribute('y', 2); p.setAttribute('width', 3); p.setAttribute('height', 3); p.setAttribute('class', 'pupila'); s.appendChild(p);
    return s;
  }
  function ojo(encendido, texto) {
    var m = mono();
    if (encendido) {
      S.ojo++;
      if (!R.ojo) { R.ojo = nodo('div', 'wsmm-ojo'); R.ojo.appendChild(icoOjo()); R.ojoTxt = nodo('span'); R.ojo.appendChild(R.ojoTxt); }
      acomodar(function () {
        R.ojoTxt.textContent = texto || 'mirando tu ventana';
        if (R.ojo._sale) R.ojo._sale();                    /* si salía, se queda: no se anima otra vez */
        if (!R.ojo.parentNode) R.caja.appendChild(R.ojo);
      });
      if (m && S.ojo === 1) { S.ojoAntes = { quieto: m.quieto }; m.quieto = true; m.tabre = 1.2; m.tgx = -4.5; m.tgy = -3.5; }
      try { WSM.unIndicador(); } catch (e) { }                 /* mientras mira, el ojito es el indicador */
      try { WSM.leyo({ texto: texto || '' }); } catch (e) { }
    } else {
      S.ojo = Math.max(0, S.ojo - 1);
      if (S.ojo || !R.ojo || !R.ojo.parentNode) return;
      var o = R.ojo;
      quitar(o, 320, function () { if (!S.ojo) o.remove(); });
      if (m) { m.quieto = S.ojoAntes ? S.ojoAntes.quieto : false; m.tabre = 1; m.tgx = 0; m.tgy = 0; if (m.parpadea) m.parpadea(true); }
      try { WSM.unIndicador(); } catch (e) { }
    }
  }

  /* ---------- el nido vacío mientras vuela a señalar ---------- */
  /* Si nadie lo trae de regreso (la app no avisó el final), a los 85 s regresa solo y le pide a la app que corte el
     vuelo: el nido nunca se queda vacío. La app corta antes (su propio reloj, a la medida de cada vuelo: ≤ 70 s). */
  var GUARDIA_MS = 85000;
  function fuera() {
    var r = WSM.piezas(), yo = r.yo, nido = r.nido;
    return !!(S.fuera || (nido && nido.classList.contains('vacio')) || (yo && yo.style.visibility === 'hidden'));
  }
  function salir(puf) {
    var r = WSM.piezas(), yo = r.yo, nido = r.nido, m = mono();
    if (!yo || !m) return JSON.stringify(null);
    var b = yo.getBoundingClientRect();
    if (!S.fuera) {
      S.fuera = { antes: (WSM.s && WSM.s.estado) || 'reposo' };
      try { WSM.estado('senalando'); } catch (e) { }
      if (WSM.s) WSM.s.vuela = true;               /* que la burbuja no se mueva mientras vuela */
    }
    if (puf && yo.animate && !WSM.quieto()) {
      var a = yo.animate([{ transform: 'scale(1)', opacity: 1 }, { transform: 'scale(0)', opacity: 0 }], { duration: 240, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' });
      a.onfinish = function () { yo.style.visibility = 'hidden'; a.cancel(); };
    } else yo.style.visibility = 'hidden';
    if (nido) nido.classList.add('vacio');
    clearTimeout(S.guardia);
    S.guardia = setTimeout(function () { S.guardia = null; if (fuera()) { host({ op: 'volver' }); volver(true); } }, GUARDIA_MS);
    return JSON.stringify({ c: m.c, f: m.f, x: b.left, y: b.top, w: b.width, h: b.height });
  }
  function volver(pop) {
    clearTimeout(S.guardia); S.guardia = null;
    if (!fuera()) return;                                    /* ya está en su nido: nada (ni un brinco de más) */
    var r = WSM.piezas(), yo = r.yo, nido = r.nido, m = mono();
    if (yo) {
      yo.style.visibility = '';
      if (pop && yo.animate && !WSM.quieto()) yo.animate([{ transform: 'scale(0)' }, { transform: 'scale(1.1)', offset: .6 }, { transform: 'scale(1)' }], { duration: 420, easing: 'cubic-bezier(.2,.9,.25,1.15)' });
    }
    if (nido) nido.classList.remove('vacio');
    if (m) { m.quieto = false; m.tgx = 0; m.tgy = 0; m.sx = 1.14; m.sy = .86; }
    if (S.fuera) {
      var antes = S.fuera.antes; S.fuera = null;
      try { WSM.aterrizar(antes); } catch (e) { if (WSM.s) WSM.s.vuela = false; }
    }
  }

  M.fuera = fuera;
  M.montar = montar; M.piezas = piezas; M.permiso = permiso; M.permisoEstado = permisoEstado;
  M.permisoCerrar = function (d) { cerrar(d.id); };
  M.ojo = ojo; M.salir = salir; M.volver = volver; M.s = S;
  return M;
})();
