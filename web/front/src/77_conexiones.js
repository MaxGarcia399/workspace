/* ================= Configuración → Conexiones: lo de adentro, cómo Workspace se conecta con cada motor =================
   Conexiones en verde (F5): el chequeo rápido (arquitectura/chequeo, GET /api/v2/chequeo), sin IA. Arriba «Workspace por
   dentro» en una línea y «Revisar ahora»; una pestaña por motor instalado; cinco filas por motor con tres estados
   (✓ funciona · ⚠ algo que solo tú puedes hacer · ✗ roto) y UNA acción por fila: Arreglar (solo lo de Workspace, con
   Deshacer), Abrir en el cliente oficial (iniciar sesión, confiar en Codex) o Reportar (un zip local: nada se envía).
   Lo que un motor no usa o no se puede revisar no aparece. La matriz de la prueba a fondo (vxLab, más abajo) queda solo
   en modo desarrollador. Mientras revisa, se vuelve a preguntar cada CX_SONDEO_MS con esta sección abierta. */
var CX = { d: null, t: 0, cargando: false, motor: '', lab: false, reloj: null };
var CX_SONDEO_MS = 2500, CX_FRESCO_MS = 5000;
var CX_EST = { ok: ['ok', '✓', 'Funciona'], tuyo: ['conf', '⚠', 'Algo que solo tú puedes hacer'], roto: ['mal', '✗', 'Roto'] };
function cxEst(e) { return CX_EST[e] || CX_EST.ok; }
function cxChip(e) { var x = cxEst(e), c = el('span', 'vx5 ' + x[0], x[1]); c.setAttribute('aria-hidden', 'true'); return c; }
function cxEnLaSeccion(C) { return C.isConnected && C.dataset.sec === 'Conexiones'; }
function cxNombre(m) { return String(m.nombre || m.motor || '').replace(' CLI', '').replace(' (V3)', ''); }
function conexiones(C, re) {
  if (CX.lab) { vxLab(C, re); return; }
  C.appendChild(el('h2', null, 'Conexiones'));
  C.appendChild(el('p', 'cs', 'Lo de adentro: cómo Workspace se conecta con cada motor. Se revisa sola al abrir, sin IA y en segundos.'));
  var d = CX.d;
  if (!CX.cargando && (!d || Date.now() - CX.t > CX_FRESCO_MS)) cxCargar(C, re);
  if (!d || (!d.workspace && !(d.motores || []).length)) { C.appendChild(el('p', 'cs vx5-carga', 'Revisando cómo está Workspace en cada motor…')); if (d && d.revisando) cxSondear(C, re); return; }
  cxArriba(C, re, d);
  var ms = d.motores || [];
  if (!ms.length) { cfgGrupo(C, null, [cfgFila('No hay motores instalados en esta computadora', 'Instala uno en Configuración → Motores.', null)]); return; }
  var m = ms.filter(function (x) { return x.motor === CX.motor; })[0] || ms.filter(function (x) { return x.estado !== 'ok'; })[0] || ms[0];
  CX.motor = m.motor;
  cxPestanas(C, re, ms, m);
  cxFilas(C, re, m);
  if (m.cambio) cxCambio(C, re, m);
  if (m.sin_pagina) C.appendChild(el('p', 'cs cxv-sin', 'La página: ' + m.sin_pagina));
  var tus = m.tus_mcp, txt = tus == null ? 'No pude leer su archivo de MCP; ábrelo en ' + cxNombre(m) + '.' : (tus.length ? tus.join(', ') : 'Ninguno. Los agregas en ' + cxNombre(m) + '; Workspace solo los lee.');
  cfgGrupo(C, 'Tus MCP en ' + cxNombre(m), [cfgFila(tus && tus.length ? tus.length + (tus.length === 1 ? ' servidor' : ' servidores') : 'Tus MCP', txt, null)]);
  if (d.dev) { var lab = cfgBoton('Prueba a fondo (laboratorio) ›', function (e) { if (e) e.stopPropagation(); CX.lab = true; re(); }); lab.classList.add('cxv-lab'); C.appendChild(lab); }
  if (d.revisando) cxSondear(C, re);
}
function cxCargar(C, re) {
  CX.cargando = true;
  api('/api/v2/chequeo').then(function (d) {
    CX.cargando = false;
    var antes = CX.d && CX.d.revisando;
    CX.d = d; CX.t = Date.now();
    if (antes && !d.revisando) nota('Listo: Conexiones revisada.');
    if (cxEnLaSeccion(C)) re();
  }, function (e) {
    CX.cargando = false;
    if (!cxEnLaSeccion(C)) return;
    if (!CX.d && e && e.actualizando) { cxActualizando(C, re); return; }
    if (!CX.d) { C.appendChild(el('p', 'cs vx5-carga mal', 'No pude revisar Conexiones: ' + e.message)); return; }
    nota(e.message, true);
  });
}
/* La página que sirve es de antes de una actualización (aún no trae el chequeo): la línea amable, «Reintentar» y otra
   vuelta sola en unos segundos (el hub la renueva en cuanto queda libre) */
function cxActualizando(C, re) {
  var v = C.querySelector('.vx5-carga'); if (v) v.remove();
  C.appendChild(el('p', 'cs vx5-carga', ACTUALIZANDO));
  C.appendChild(cfgBoton('Reintentar', function (e) { if (e) e.stopPropagation(); CX.t = 0; re(); }));
  clearTimeout(CX.reloj); CX.reloj = setTimeout(function () { if (cxEnLaSeccion(C)) { CX.t = 0; re(); } }, 8000);
}
function cxSondear(C, re) {
  clearTimeout(CX.reloj);
  CX.reloj = setTimeout(function () { if (cxEnLaSeccion(C)) { CX.t = 0; cxCargar(C, re); } }, CX_SONDEO_MS);
}
/* «Workspace por dentro» en una línea, con «Revisar ahora»; y el aviso del último arreglo con su «Deshacer» */
function cxArriba(C, re, d) {
  var w = d.workspace || { estado: 'ok', texto: 'Workspace por dentro', detalle: '' };
  var b = el('button', 'btc', d.revisando ? 'Revisando…' : 'Revisar ahora');
  b.disabled = !!d.revisando;
  b.onclick = function (e) { e.stopPropagation(); b.disabled = true; post('/api/v2/chequeo/revisar', {}).then(function () { nota('Revisando, sin IA: unos segundos'); CX.t = 0; CX.d.revisando = true; re(); }, function (e2) { nota(e2.message, true); b.disabled = false; }); };
  var desc = (w.detalle ? w.detalle + ' · ' : '') + (d.revisando ? 'revisando ahora…' : (d.hace ? 'revisado al abrir ' + d.hace : ''));
  var filas = [cfgFila(w.texto || 'Workspace por dentro', desc, w.accion ? cxBoton(re, w.accion, '', '') : b)];
  filas[0].insertBefore(cxChip(w.estado), filas[0].firstChild);
  if (d.prueba_a_fondo) filas.push(cfgFila('Prueba a fondo', d.prueba_a_fondo, null));   /* F6: el canario, solo en nuestras máquinas */
  var av = (d.avisos || [])[(d.avisos || []).length - 1];
  if (av) {
    var dh = null;
    if (av.deshacer) { dh = cfgBoton('Deshacer', function (e) { if (e) e.stopPropagation(); dh.disabled = true; post('/api/v2/chequeo/deshacer', { id: av.deshacer }).then(function (r) { nota(r.texto || 'Listo'); CX.t = 0; re(); }, function (e2) { nota(e2.message, true); dh.disabled = false; }); }); }
    var r = cfgFila(av.ok ? 'Workspace lo arregló solo' : 'Workspace intentó arreglarlo', av.texto || '', dh);
    r.insertBefore(cxChip(av.ok ? 'ok' : 'tuyo'), r.firstChild);
    filas.push(r);
  }
  cfgGrupo(C, null, filas).style.marginTop = '20px';
}
function cxPestanas(C, re, ms, m) {
  var w = C.appendChild(el('div', 'cxv-chips'));
  ms.forEach(function (x) {
    var b = el('button', 'cxv-chip' + (x === m ? ' on' : ''));
    b.appendChild(el('span', null, cxNombre(x))); b.appendChild(cxChip(x.estado));
    b.title = cxNombre(x) + ': ' + cxEst(x.estado)[2];
    b.onclick = function (e) { e.stopPropagation(); CX.motor = x.motor; re(); };
    w.appendChild(b);
  });
}
function cxFilas(C, re, m) {
  var titulo = 'Lo de adentro de ' + cxNombre(m) + (m.version ? ' · ' + m.version + (m.version_estado ? ' · ' + m.version_estado : '') : '');
  cfgGrupo(C, titulo, (m.filas || []).map(function (f) {
    var r = cfgFila(f.nombre, f.texto, f.accion ? cxBoton(re, f.accion, m.motor, f.id) : null);
    r.insertBefore(cxChip(f.estado), r.firstChild);
    r.classList.add('cxv-' + f.estado);
    return r;
  }));
}
/* la tarjeta «se actualizó» del motor (la revisión al abrir): una línea si todo sigue bien; si no, sus tres botones */
function cxCambio(C, re, m) {
  var c = m.cambio, caja = C.appendChild(el('div', 'cxv-cambio ' + (c.estado === 'ok' ? 'bien' : 'mal')));
  caja.appendChild(el('p', null, (c.estado === 'ok' ? '↑ ' : '') + c.texto));
  if (!(c.botones || []).length) return;
  var acts = caja.appendChild(el('div', 'cfg-acciones'));
  c.botones.forEach(function (k) {
    if (k === 'otro') acts.appendChild(cfgBoton(c.alternativa ? 'Seguir con ' + motorN(c.alternativa) : 'Seguir con otro motor', function (e) { if (e) e.stopPropagation(); configuracion('Motores'); nota(c.alternativa ? 'Elige ' + motorN(c.alternativa) + ' como motor de tus agentes' : 'Elige otro motor'); }));
    if (k === 'reportar') acts.appendChild(cxBoton(re, { tipo: 'reportar', etiqueta: 'Reportar' }, m.motor, ''));
    if (k === 'revisar') acts.appendChild(cfgBoton('Volver a revisar', function (e) { if (e) e.stopPropagation(); post('/api/v2/chequeo/revisar', { motor: m.motor }).then(function () { nota('Revisando ' + cxNombre(m) + '…'); CX.t = 0; CX.d.revisando = true; re(); }, function (e2) { nota(e2.message, true); }); }));
  });
}
/* la única acción de una fila: Arreglar (lo de Workspace) · Abrir en el cliente oficial (login, confiar en Codex) · Reportar */
function cxBoton(re, ac, motor, fila) {
  var b = cfgBoton(ac.etiqueta || 'Arreglar', function (e) {
    if (e) e.stopPropagation();
    if (b.disabled) return;
    if (ac.tipo === 'arreglar') {
      b.disabled = true;
      post('/api/v2/chequeo/arreglar', { arreglo: ac.arreglo }).then(function (r) { nota(r.texto || 'Listo'); CX.t = 0; re(); }, function (e2) { nota(e2.message, true); b.disabled = false; });
    } else if (ac.tipo === 'reportar') {
      b.disabled = true;
      post('/api/v2/chequeo/reportar', { motor: motor || '', fila: fila || '' }).then(function (r) {
        nota(r.texto || 'Listo', !r.ok, 6000);
        try { if (r.resumen && navigator.clipboard) navigator.clipboard.writeText(r.resumen); } catch (_) {}
        b.disabled = false;
      }, function (e2) { nota(e2.message, true); b.disabled = false; });
    } else if (ac.abrir === 'confiar' && ac.agente) {
      b.disabled = true;
      post('/api/v2/arreglar', { agente: ac.agente, accion: 'confiar_hooks' }).then(function () { nota('Se abrió Codex en su terminal: escribe /hooks y confía en los de Workspace'); b.disabled = false; }, function (e2) { nota(e2.message, true); b.disabled = false; });
    } else {
      var v = document.querySelector('.velo'); if (v) v.remove();
      configuracion('Motores');
      nota((ac.abrir === 'login' ? 'Inicia sesión en ' : 'Ábrelo en ') + motorN(ac.motor || motor) + ' desde su ficha');
    }
  });
  b.classList.add(ac.tipo === 'arreglar' ? 'cxv-arreglar' : (ac.tipo === 'reportar' ? 'cxv-reportar' : 'cxv-abrir'));
  return b;
}

/* ================= La vista de laboratorio (solo modo desarrollador): la matriz de la prueba a fondo =================
   La última verificación REAL (arquitectura/verificacion, GET /api/v2/conexiones), el mismo backend de la página de
   antes: arriba lo que comparten todos los motores; abajo la matriz pieza × motor instalado, con su fecha. */
var VX = { d: null, t: 0, cargando: false, sel: '', reloj: null, corria: false };
var VX_SONDEO_MS = 3000, VX_FRESCO_MS = 5000;
/* los cinco estados: su clase, su marca y lo que quiere decir («no se usa» es neutro: nunca rojo ni alarma) */
var VX_EST = {
  ok: ['ok', '✓', 'Funciona'],
  falla: ['mal', '✗', 'Falló'],
  no_se_usa: ['no', '–', 'No se usa en ese motor (no es un error)'],
  confianza: ['conf', '!', 'Falta tu confianza una vez'],
  sin_verificar: ['nada', '?', 'Sin verificar todavía']
};
var VX_ORDEN = ['ok', 'falla', 'no_se_usa', 'confianza', 'sin_verificar'];
function vxEst(e) { return VX_EST[e] || VX_EST.sin_verificar; }
function vxChip(e) { var x = vxEst(e), c = el('span', 'vx5 ' + x[0], x[1]); c.setAttribute('aria-hidden', 'true'); return c; }
function vxMayus(t) { t = String(t || ''); return t.charAt(0).toUpperCase() + t.slice(1); }
function vxTexto(c) { return vxMayus(c.texto || vxEst(c.estado)[2]); }
/* su fecha viene en ISO, en la hora de esta computadora */
function vxCuando(f) { var t = typeof f === 'number' ? f : Date.parse(f || ''); return t ? cuando(t) : ''; }
function vxEnLaSeccion(C) { return C.isConnected && C.dataset.sec === 'Conexiones'; }
function vxLab(C, re) {
  C.appendChild(el('h2', null, 'Conexiones · laboratorio'));
  var volver = el('button', 'cxv-volver', '‹ Volver a Conexiones');
  volver.type = 'button';
  volver.onclick = function (e) { if (e) e.stopPropagation(); CX.lab = false; re(); };
  C.appendChild(volver);
  C.appendChild(el('p', 'cs', 'La prueba a fondo con el motor real (solo en nuestras máquinas): cada pieza, motor por motor, según su última verificación.'));
  var d = VX.d;
  if (!VX.cargando && (!d || Date.now() - VX.t > VX_FRESCO_MS)) vxCargar(C, re);
  if (!d) { C.appendChild(el('p', 'cs vx5-carga', 'Leyendo la última verificación…')); return; }
  vxEstado(C, re, d);
  vxComunes(C, d);
  vxMatriz(C, re, d);
  if (d.corriendo) vxSondear(C, re);
}
function vxCargar(C, re) {
  VX.cargando = true;
  api('/api/v2/conexiones').then(function (d) {
    VX.cargando = false;
    if (VX.corria && !d.corriendo) nota('Terminó la verificación: aquí está lo que vio.');
    VX.d = d; VX.t = Date.now(); VX.corria = !!d.corriendo;
    if (vxEnLaSeccion(C)) re();
  }, function (e) {
    VX.cargando = false;
    if (!vxEnLaSeccion(C)) return;
    if (!VX.d) { C.appendChild(el('p', 'cs vx5-carga mal', 'No pude leer la verificación: ' + e.message)); return; }
    nota(e.message, true);
  });
}
/* mientras corre: se vuelve a preguntar, solo si sigues en Conexiones (un reloj a la vez) */
function vxSondear(C, re) {
  clearTimeout(VX.reloj);
  VX.reloj = setTimeout(function () { if (vxEnLaSeccion(C)) { VX.t = 0; vxCargar(C, re); } }, VX_SONDEO_MS);
}
/* cómo va: corriendo (con su avance en simple) o cuándo fue la última; y «Verificar ahora» */
function vxEstado(C, re, d) {
  var b = el('button', 'btc', d.corriendo ? 'Verificando…' : 'Verificar ahora');
  b.disabled = !!d.corriendo;
  b.onclick = function (e) { e.stopPropagation(); vxVerificar(C, re, b); };
  var titulo, desc, p = d.progreso || {}, n = Number(p.hecho) || 0, t = Number(p.total) || 0;
  if (d.corriendo) {
    titulo = t && p.actual ? 'Verificando ' + p.actual + '… ' + n + ' de ' + t : 'Preparando la verificación…';
    desc = 'Un turno corto por motor y por camino (terminal y página). Puedes seguir trabajando mientras tanto.';
  } else if (d.fecha) {
    titulo = 'Última verificación: ' + vxCuando(d.fecha);
    desc = 'Corre un turno corto en cada motor instalado, por la terminal y por la página, y mira lo que de verdad pasó.';
  } else {
    titulo = 'Todavía no hay una verificación real';
    desc = 'Toca «Verificar ahora»: corre un turno corto en cada motor instalado y mira lo que de verdad pasó.';
  }
  var fila = cfgFila(titulo, desc, b);
  if (d.fecha && !d.corriendo) fila.querySelector('b').title = String(d.fecha).replace('T', ' ');
  if (d.corriendo && t) { var bar = el('div', 'ubar'), i = el('i'); i.style.width = Math.min(100, Math.round(100 * n / t)) + '%'; bar.appendChild(i); fila.querySelector('.t').appendChild(bar); }
  cfgGrupo(C, null, [fila]).style.marginTop = '20px';
}
/* «Verificar ahora»: si no empezó (ya hay una corriendo, o no pudo), su porqué en una nota; luego se ve cómo va */
function vxVerificar(C, re, b) {
  b.disabled = true;
  post('/api/v2/verificar', {}).then(function () {
    VX.corria = true; VX.t = 0; nota('Empezó la verificación'); if (vxEnLaSeccion(C)) re();
  }, function (e) { nota(e.message, true); VX.t = 0; if (vxEnLaSeccion(C)) re(); });
}
/* su línea: qué pasa y por qué; qué hacer, si hay algo; y cuándo se vio */
function vxDesc(c) {
  var s = vxTexto(c) + (c.por_que ? ' · ' + c.por_que : '');
  if (c.fecha) s += ' · verificado ' + vxCuando(c.fecha);
  return s;
}
function vxQueHacer(c, padre) {
  if (c.que_hacer) padre.appendChild(el('small', 'vx5-hacer ' + vxEst(c.estado)[0], c.que_hacer));
}
function vxComunes(C, d) {
  var cs = d.comunes || [];
  if (!cs.length) return;
  var ok = cs.filter(function (c) { return c.estado === 'ok'; }).length;
  cfgGrupo(C, 'Lo que comparten todos los motores · ' + ok + ' de ' + cs.length, cs.map(function (c) {
    var r = cfgFila(c.nombre, vxDesc(c), null);
    r.insertBefore(vxChip(c.estado), r.firstChild);
    vxQueHacer(c, r.querySelector('.t'));
    return r;
  }));
}
function vxMatriz(C, re, d) {
  var ms = d.motores || [], ss = d.sistemas || [];
  var inst = ms.filter(function (m) { return m.instalado; }), fuera = ms.filter(function (m) { return !m.instalado; });
  C.appendChild(el('div', 'cg', 'Pieza por motor · ' + (inst.length === 1 ? '1 motor instalado' : inst.length + ' motores instalados')));
  var caja = C.appendChild(el('div', 'cc vx5-caja'));
  if (!inst.length) caja.appendChild(cfgFila('No hay motores instalados en esta computadora', 'Instala uno (Configuración → Motores) y vuelve a verificar.', null));
  else vxTabla(caja, inst, ss);
  var ley = C.appendChild(el('div', 'vx5-ley'));
  VX_ORDEN.forEach(function (e) { var x = el('span'); x.appendChild(vxChip(e)); x.appendChild(document.createTextNode(vxEst(e)[2])); ley.appendChild(x); });
  if (fuera.length) C.appendChild(el('p', 'cs', 'No instalados: ' + fuera.map(function (m) { return m.nombre; }).join(', ') + '.'));
}
function vxTabla(caja, inst, ss) {
  var scroll = caja.appendChild(el('div', 'vx5-scroll')), tabla = scroll.appendChild(el('table', 'vx5t'));
  var cab = el('tr'), th0 = el('th', 'vx5-s', 'Pieza'); th0.setAttribute('scope', 'col'); cab.appendChild(th0);
  inst.forEach(function (m) {
    var th = el('th'); th.setAttribute('scope', 'col'); th.appendChild(el('b', null, m.nombre));
    th.appendChild(el('small', null, m.fecha ? vxCuando(m.fecha) : 'sin verificar')); cab.appendChild(th);
  });
  tabla.appendChild(el('thead')).appendChild(cab);
  var tb = tabla.appendChild(el('tbody')), det = el('div', 'vx5-det'), elegida = null;
  ss.forEach(function (s) {
    var fila = tb.appendChild(el('tr')), th = el('th', 'vx5-s', s.nombre); th.setAttribute('scope', 'row'); fila.appendChild(th);
    inst.forEach(function (m) {
      var c = (m.celdas || {})[s.id] || { estado: 'sin_verificar' }, clave = m.motor + '|' + s.id;
      var b = el('button', 'vx5b' + (VX.sel === clave ? ' sel' : ''));
      b.title = vxTexto(c); b.setAttribute('aria-label', s.nombre + ' en ' + m.nombre + ': ' + vxTexto(c));
      b.appendChild(vxChip(c.estado));
      if (c.via) b.appendChild(el('small', null, c.via));
      b.onclick = function (e) {
        e.stopPropagation(); VX.sel = clave;
        tabla.querySelectorAll('.vx5b.sel').forEach(function (x) { x.classList.remove('sel'); });
        b.classList.add('sel'); vxDetalle(det, s, m, c);
      };
      var td = el('td'); td.appendChild(b); fila.appendChild(td);
      if (VX.sel === clave) elegida = [s, m, c];
    });
  });
  caja.appendChild(det);
  if (elegida) vxDetalle(det, elegida[0], elegida[1], elegida[2]);
  else det.appendChild(el('small', 'vx5-toca', 'Toca una casilla para ver qué pasa ahí.'));
}
/* lo de una casilla, debajo de la matriz; por camino (terminal y página) solo si no dicen lo mismo */
function vxDetalle(det, s, m, c) {
  det.textContent = '';
  var h = det.appendChild(el('div', 'vx5-dh')); h.appendChild(vxChip(c.estado)); h.appendChild(el('b', null, s.nombre + ' en ' + m.nombre));
  if (c.via) h.appendChild(el('code', null, c.via));
  det.appendChild(el('p', null, vxDesc(c)));
  vxQueHacer(c, det);
  var cs = c.caminos || {}, ks = Object.keys(cs);
  if (ks.length > 1 && ks.some(function (k) { return (cs[k] || {}).estado !== (cs[ks[0]] || {}).estado; })) {
    var w = det.appendChild(el('div', 'vx5-cam'));
    ks.forEach(function (k) {
      var x = cs[k] || {}, sp = el('span'); sp.title = x.detalle || ''; sp.appendChild(vxChip(x.estado));
      sp.appendChild(document.createTextNode(k === 'terminal' ? 'Terminal' : k === 'pagina' ? 'Página' : k)); w.appendChild(sp);
    });
  }
}
