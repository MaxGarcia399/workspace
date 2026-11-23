/* ================= actuar en la burbuja (A0, seguridad primero) =================
   Lo de actuar que vive en la burbuja (la tarjeta de OK NO: esa la arma la app, en su propia ventanita, con lo que dice
   el sistema). Va en la misma caja que las manos (25_manos.js), con sus mismas zonas de clic y su mismo movimiento:
     · el interruptor de la barra «Si te pido algo: en segundo plano · a la vista» (de fábrica, en segundo plano);
     · el aviso tranquilo de lo que hizo en segundo plano, con Deshacer (o «Cerrar», lo que diga la app) y «Enséñame»; en
       A0 dice «Ensayo»;
     · la pastilla «Haciendo 2 de 3» y, al final, «Listo · Deshacer»;
     · el número y el brinco de las fichas de la app (lo que espera tu clic: WSMActuar.fichas, fichaLlego);
     · el toque del monito cuando terminó.
       El aviso y el toque NO tienen pieza propia: son EL toque de las entregas (27_entregas.js: el brinco, el globito
       junto al nido y el número), el mismo de un encargo que terminó. Un solo globito, un solo número;
     · la tarjeta amable antes del aviso de Automatización de macOS (una vez por app, solo si hace falta).
   Lo que eliges sale por el `host` de la burbuja con op «actuar_*»: lo atiende la app, no va al puente. Todo con
   textContent: nada de lo que viene se interpreta como HTML. */
var WSMActuar = (function () {
  var S = { prendido: false, modos: {} };
  var M = { alHost: null };
  var R = {};
  var MODOS = [['segundo_plano', 'en segundo plano'], ['a_la_vista', 'a la vista']];
  var ESPERA_AVISO_MS = 12000;
  var OK_MS = 75000;                     /* lo que espera la tarjeta de OK de la app (luego vence) */

  function host(op) {
    if (M.alHost) { try { M.alHost(op); } catch (e) { } return; }
    try { WSM.host(op); } catch (e) { }
  }
  function nodo(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
  function mono() { try { return WSM.mono(); } catch (e) { return null; } }
  function quieto() { try { return WSM.quieto(); } catch (e) { return false; } }
  function caja() { try { return WSM.piezas().manos || null; } catch (e) { return null; } }
  function barra() { try { return WSM.piezas().barra || null; } catch (e) { return null; } }
  function elegido() { try { return (WSM.s && WSM.s.elegido) || ''; } catch (e) { return ''; } }
  function acomodar(fn) { try { WSM.acomodar(fn); } catch (e) { fn(); } }
  function quitar(n, ms, fn) { try { WSM.salir(n, ms, fn); } catch (e) { fn(); } }

  /* ---------- el interruptor de la barra: cómo lo hace si le pides algo ---------- */
  function puede() {
    /* A1: lo de verdad es por agente (S.agentes, los que tienen «Puede hacer cosas en mi Mac»); el ensayo, para todos */
    return S.prendido && (!S.agentes || S.agentes.indexOf(elegido()) >= 0);
  }
  function interruptor() {
    var b = barra();
    if (!b || !puede()) { if (R.modo && R.modo.parentNode) R.modo.remove(); return; }
    if (!R.modo) {
      R.modo = nodo('div', 'wsma-modo');
      R.modo.appendChild(nodo('span', 'wsma-modo-t', 'Si te pido algo:'));
      R.botones = {};
      MODOS.forEach(function (m) {
        var x = nodo('button', 'wsma-op', m[1]);
        x.onclick = function () { host({ op: 'actuar_modo', agente: elegido(), modo: m[0] }); pintarModo(m[0]); };
        R.botones[m[0]] = x; R.modo.appendChild(x);
      });
    }
    if (!R.modo.parentNode) b.insertBefore(R.modo, b.lastChild);
    pintarModo(S.modos[elegido()] || 'segundo_plano');
  }
  function pintarModo(m) {
    if (!R.botones) return;
    S.modos[elegido()] = m;
    MODOS.forEach(function (x) { R.botones[x[0]].classList.toggle('on', x[0] === m); });
  }
  function disponible(d) {
    S.prendido = !!(d && d.prendido);
    S.etapa = (d && d.etapa) || '';
    S.agentes = d && Array.isArray(d.agentes) ? d.agentes.map(String) : null;
    var ms = (d && d.modos) || {};
    for (var k in ms) if (Object.prototype.hasOwnProperty.call(ms, k)) S.modos[k] = String(ms[k]);
    interruptor();
  }
  function modo(d) { if (d && d.agente) { S.modos[d.agente] = d.modo; if (d.agente === elegido()) pintarModo(d.modo); } }

  /* ---------- el aviso tranquilo (segundo plano): en el globito del toque, con Deshacer, y se va solo ---------- */
  function E() { return typeof WSMEntregas !== 'undefined' && WSMEntregas.toque ? WSMEntregas : null; }
  function nombre(id) { var e = E(); return id ? (e ? e.nombre(id) : id) : ''; }
  function aviso(d) {
    var e = E(); if (!e || !d) return;
    var id = String(d.id || 'aviso'), chips = [];
    if (d.deshacer) chips.push([String(d.boton || 'Deshacer'), function () { host({ op: 'actuar_deshacer', id: id }); }, true]);
    if (d.ensename) chips.push(['Enséñame', function () { host({ op: 'actuar_ensename', id: id }); }]);
    e.toque({ clave: 'actuar:' + id, agente: d.agente || elegido(), tipo: 'aviso', titulo: nombre(d.agente || elegido()) || 'Tu Compañero',
      sub: String(d.texto || ''), chips: chips, ensayo: !!d.ensayo, largo: true, ms: ESPERA_AVISO_MS });
  }
  function cerrarAviso(id) { var e = E(); if (e) e.cerrarToque('actuar:' + String(id || 'aviso')); }

  /* ---------- las fichas de la app (ronda 2 · bloque P) ----------
     Lo que espera tu clic ya no vive en la burbuja: son fichas de la app, pegadas al monito (Bandeja.swift). Aquí solo
     llega su cuenta (el número del nido: el mismo de las entregas) y el brinco de «te necesita» cuando llega una. La
     lista (solo datos de la app) se la queda WSFichas (28_fichas.js) para quien la quiera pintar (el chat grande). */
  function fichas(d) {
    var e = E(), n = Math.max(0, Math.min(99, +(d && d.n) || 0)), antes = S.fichasN || 0;
    S.fichasN = n; S.fichasPlegada = !!(d && d.plegada);
    if (e) for (var i = 0; i < Math.max(n, antes); i++) e.cuenta('ficha-' + i, i < n);
    if (typeof WSFichas !== 'undefined') WSFichas.poner(d);
  }
  function fichaLlego() {
    var e = E();
    if (e) { e.gesto('necesita'); return; }
    var m = mono(); if (!m || quieto()) return;
    m.salta(.8); if (m.signo) m.signo('pregunta', { donde: 'der', esc: .8 });
  }

  /* ---------- la pastilla «Haciendo 2 de 3» ---------- */
  function avance(d) {
    var c = caja(); if (!c || !d) return;
    if (!R.pastilla) { R.pastilla = nodo('div', 'wsma-pastilla'); R.pastillaTxt = nodo('span'); R.parar = nodo('button', 'chip', 'Parar');
      R.parar.onclick = function () { host({ op: 'actuar_parar' }); }; R.pastilla.appendChild(R.pastillaTxt); R.pastilla.appendChild(R.parar); }
    var hecho = Math.max(0, +d.hecho || 0), de = Math.max(1, +d.de || 1);
    acomodar(function () {
      if (!R.pastilla.parentNode) c.appendChild(R.pastilla);
      R.pastillaTxt.textContent = hecho >= de ? 'Listo' : 'Haciendo ' + Math.max(1, hecho + 1) + ' de ' + de;
      R.parar.hidden = hecho >= de;
    });
    if (hecho >= de) { var p = R.pastilla; setTimeout(function () { quitar(p, 320, function () { p.remove(); }); }, 2400); }
  }

  /* ---------- el toque del monito: necesita tu OK o terminó (EL toque de 27_entregas.js) ----------
     'ok': el brinco de «te necesita», el globito «Luna necesita tu OK · ¿Escribo en Mail?» y +1 en el número mientras
     la tarjeta de la app espera. El globito no contesta nada: el OK solo está en la tarjeta de la app.
     'listo': el brinco de «terminó»; su globito es el aviso tranquilo (aviso(), que llega justo antes). */
  function toca(que, d) {
    var e = E();
    if (!e) {                                                   /* sin las entregas: solo el brinco (como antes) */
      var m = mono(); if (!m || quieto()) return;
      if (que === 'ok') { m.salta(.8); if (m.signo) m.signo('pregunta', { donde: 'der', esc: .8 }); }
      else { m.salta(1.05); if (m.rafaga) m.rafaga(5); }
      return;
    }
    if (que !== 'ok') { e.gesto('termino'); return; }
    d = d || {};
    var a = d.agente || elegido();
    e.cuenta('actuar-ok', true);
    e.toque({ clave: 'actuar-ok', agente: a, tipo: 'necesita', titulo: (nombre(a) || 'Tu Compañero') + ' necesita tu OK',
      sub: (d.titulo ? String(d.titulo) + ' · ' : '') + 'en su tarjeta', ms: OK_MS });
  }
  /* la tarjeta de OK se cerró (la contestaste, venció, cambió la ventana o paraste todo): baja el número y, si el
     globito sigue siendo el suyo, se va (si ya llegó el aviso, el aviso se queda: se cruzó encima) */
  function okCerrado() { var e = E(); if (!e) return; e.cuenta('actuar-ok', false); e.cerrarToque('actuar-ok'); }

  /* ---------- Automatización: la tarjeta amable antes del aviso de macOS ---------- */
  function permiso(d) {
    var c = caja(); if (!c || !d) return;
    if (!R.perm) {
      R.perm = nodo('div', 'wsmm-tarjeta wsma-perm');
      var cab = nodo('div', 'wsmm-cab'); cab.appendChild(nodo('b', null, 'Permiso de la Mac'));
      R.permTxt = nodo('p', 'wsmm-txt'); R.permChips = nodo('div', 'chips');
      [cab, R.permTxt, R.permChips].forEach(function (k) { R.perm.appendChild(k); });
    }
    var b = String(d.bundle || '');
    acomodar(function () {
      if (!R.perm.parentNode) c.insertBefore(R.perm, c.firstChild);
      R.perm.classList.remove('gracias');
      R.permTxt.textContent = String(d.texto || '');
      R.permChips.textContent = '';
      [[String(d.boton || 'Seguir'), 'seguir', true], ['Ahora no', 'no']].forEach(function (x) {
        var e = nodo('button', 'chip' + (x[2] ? ' p' : ''), x[0]);
        e.onclick = function () { host({ op: 'actuar_automatizar', bundle: b, accion: x[1] }); };
        R.permChips.appendChild(e);
      });
    });
  }
  function permisoEstado(d) {
    if (!R.perm || !d) return;
    acomodar(function () {
      R.permTxt.textContent = String(d.texto || '');
      R.permChips.textContent = '';
      R.perm.classList.toggle('gracias', !!d.gracias);
    });
    setTimeout(permisoCerrar, 3200);
  }
  function permisoCerrar() {
    var p = R.perm; if (!p || !p.parentNode) return;
    quitar(p, 320, function () { p.remove(); });
  }

  M.disponible = disponible; M.modo = modo; M.aviso = aviso; M.cerrarAviso = cerrarAviso; M.avance = avance;
  M.fichas = fichas; M.fichaLlego = fichaLlego;
  M.toca = toca; M.okCerrado = okCerrado; M.permiso = permiso; M.permisoEstado = permisoEstado; M.permisoCerrar = permisoCerrar;
  M.interruptor = interruptor; M.s = S;
  return M;
})();
