/* ================= archivar un agente o quitarlo de Workspace (agente_apartar · /api/front/apartados) =================
   Lo mismo que el hub (Agentes › Esta máquina): «Archivar» lo saca de las listas y «Quitar de Workspace» lo desregistra
   en esta computadora. Nada se borra: su carpeta se queda y se dice dónde. Las dos avisan en una línea con «Deshacer».
   Lo que conviene saber antes (hablas con él, es el único, tiene algo abierto, coordina a otros, su carpeta está a
   medio sincronizar) se dice al confirmar; nada bloquea. Después de cada cambio la página se vuelve a cargar: así el
   riel, las pestañas y el panel quedan como el registro, y el aviso (con su «Deshacer») sigue ahí al volver. */
var APARTADO_MS = 45000, APARTADO_LLAVE = 'ws.front.apartado';
function notaApartado(texto, nombre) {
  document.querySelectorAll('.nota.deshacer').forEach(function (n) { n.remove(); });
  var n = el('div', 'nota deshacer apartado'); n.appendChild(el('span', null, texto));
  if (nombre) {
    var b = el('button', null, 'Deshacer');
    b.onclick = function (e) {
      e.stopPropagation(); b.disabled = true;
      post('/api/front/volver', { nombre: nombre }).then(function (r) { recargarTrasApartar(r.aviso || '', ''); }, function (x) { b.disabled = false; nota(x.message, true); });
    };
    n.appendChild(b);
  }
  document.body.appendChild(n);
  setTimeout(function () { n.remove(); }, nombre ? APARTADO_MS : 6000);
}
function recargarTrasApartar(aviso, deshacer) {
  try { sessionStorage.setItem(APARTADO_LLAVE, JSON.stringify({ t: Date.now(), texto: aviso, nombre: deshacer || '' })); } catch (_) {}
  location.reload();
}
/* al arrancar: el aviso del último archivar, quitar o traer de vuelta, si es de hace un momento */
function avisoApartadoPendiente() {
  var d = null;
  try { d = JSON.parse(sessionStorage.getItem(APARTADO_LLAVE) || 'null'); sessionStorage.removeItem(APARTADO_LLAVE); } catch (_) { d = null; }
  if (d && d.texto && Date.now() - (d.t || 0) < APARTADO_MS) notaApartado(d.texto, d.nombre || '');
}
function apartadosDe(a) {
  var hablando = a && actividadDe(a).k !== 'dormido' ? '1' : '0';
  return api('/api/front/apartados' + (a ? '?agente=' + encodeURIComponent(a.id) + '&hablando=' + hablando : ''));
}
/* el bloque del panel del agente (Resumen): «Archivar» y «Quitar de Workspace», con su confirmación ahí mismo */
function bloqueApartar(C, a) {
  var l = el('div', 'lbl7'); l.appendChild(el('span', null, 'En esta computadora')); C.appendChild(l);
  var caja = el('div', 'apartar'); C.appendChild(caja);
  function opciones() {
    caja.textContent = '';
    var f1 = el('div', 'apf'), t1 = el('div', 't'); t1.appendChild(el('b', null, 'Archivar')); t1.appendChild(el('p', null, 'Sale de las listas. Su carpeta y sus sesiones se quedan; vuelve desde Configuración › General.'));
    var b1 = el('button', 'btc sec', 'Archivar'); f1.appendChild(t1); f1.appendChild(b1); caja.appendChild(f1);
    var f2 = el('div', 'apf'), t2 = el('div', 't'); t2.appendChild(el('b', null, 'Quitar de Workspace')); t2.appendChild(el('p', null, 'Deja de estar en Workspace en esta computadora. Su carpeta no se borra.'));
    var b2 = el('button', 'btc rojo', 'Quitar'); f2.appendChild(t2); f2.appendChild(b2); caja.appendChild(f2);
    b1.onclick = function () {
      b1.disabled = true;
      apartadosDe(a).then(function (d) { if ((d.avisos || []).length) confirmar('archivar', d); else hacer('archivar', b1); }, function (x) { b1.disabled = false; nota(x.message, true); });
    };
    b2.onclick = function () {
      b2.disabled = true;
      apartadosDe(a).then(function (d) { confirmar('quitar', d); }, function (x) { b2.disabled = false; nota(x.message, true); });
    };
  }
  function confirmar(que, d) {
    caja.textContent = '';
    var q = el('div', 'apq');
    q.appendChild(el('b', null, que === 'quitar' ? '¿Quitar a ' + a.n + ' de Workspace?' : '¿Archivar a ' + a.n + '?'));
    q.appendChild(el('p', null, que === 'quitar' ? 'Deja de estar en Workspace en esta computadora: su registro, su comando de la terminal y su tema.' : 'Sale de las listas y de la barra. Vuelve con un clic desde Configuración › General › Agentes archivados.'));
    (d.avisos || []).forEach(function (t) { q.appendChild(el('p', 'apav', '⚠ ' + t)); });
    q.appendChild(el('p', 'apdonde', 'Su carpeta no se borra: se queda en ' + (d.carpeta || 'su lugar') + '.'));
    var bs = el('div', 'apbs'), si = el('button', que === 'quitar' ? 'btc rojo' : 'btc', que === 'quitar' ? 'Sí, quitar' : 'Sí, archivar'), no = el('button', 'btc sec', 'Cancelar');
    si.onclick = function () { hacer(que, si); }; no.onclick = opciones;
    bs.appendChild(si); bs.appendChild(no); q.appendChild(bs); caja.appendChild(q);
  }
  function hacer(que, boton) {
    boton.disabled = true;
    post(que === 'quitar' ? '/api/front/quitar' : '/api/front/archivar', { agente: a.id }).then(
      function (r) { recargarTrasApartar(r.aviso || '', r.deshacer || ''); },
      function (x) { boton.disabled = false; nota(x.message, true); opciones(); });
  }
  opciones();
}
/* Configuración › General: los archivados, cada uno con «Traer de vuelta» (un clic) */
function cfgArchivados(C) {
  var hueco = el('div'); C.appendChild(hueco);
  api('/api/front/apartados').then(function (d) {
    var lista = d.archivados || []; if (!lista.length || !hueco.isConnected) return;
    cfgGrupo(hueco, 'Agentes archivados', lista.map(function (x) {
      var b = el('button', 'btc sec', 'Traer de vuelta');
      b.onclick = function () {
        b.disabled = true;
        post('/api/front/volver', { nombre: x.nombre }).then(function (r) { recargarTrasApartar(r.aviso || '', ''); }, function (e) { b.disabled = false; nota(e.message, true); });
      };
      return cfgFila(x.visible, 'Su carpeta: ' + x.carpeta + (x.existe ? '' : ' · todavía no está en esta computadora'), b);
    }));
  }, function () {});
}
