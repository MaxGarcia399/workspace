/* ================= configuración: el engrane de abajo del riel =================
   General, Motores, Permisos, Uso y Actualizaciones, como en el prototipo. Solo dice lo que de verdad pasa: lo que
   todavía no se puede cambiar desde aquí lo dice así, sin botones de mentira. Las preferencias de la página (enviar
   con ⌘↵, el motor de los agentes nuevos, el tema) viven en Workspace (pagGet/pagSet en 30_datos.js): la página cambia
   de puerto en cada arranque y lo guardado en el navegador se perdía. */
var CFG_PAG = { cmdEnter: 'cmd_enter', motorDef: 'motor_def', temaPredeterminado: 'tema_predeterminado', tema: 'tema' };
var CFG_LOCAL = {
  get: function (k) { if (CFG_PAG[k]) return pagGet(CFG_PAG[k]); try { return JSON.parse(localStorage.getItem('ws.cfg.' + k)); } catch (_) { return null; } },
  set: function (k, v) { if (CFG_PAG[k]) return pagSet(CFG_PAG[k], v); try { localStorage.setItem('ws.cfg.' + k, JSON.stringify(v)); } catch (_) {} }
};
/* los íconos, como piezas de SVG armadas con el DOM (la página nunca mete HTML crudo) */
var SVG_CFG = {
  General: [['path', { d: 'M4 7h9M17 7h3M4 17h3M11 17h9' }], ['circle', { cx: 15, cy: 7, r: 2.2 }], ['circle', { cx: 9, cy: 17, r: 2.2 }]],
  Motores: [['rect', { x: 2.5, y: 4, width: 19, height: 16, rx: 3 }], ['path', { d: 'm7 10 3 2-3 2M12.5 15H17' }]],
  Permisos: [['path', { d: 'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z' }]],
  Conexiones: [['path', { d: 'M10 13.5a4 4 0 0 0 6 .4l3-3a4 4 0 0 0-5.7-5.7l-1.6 1.6' }], ['path', { d: 'M14 10.5a4 4 0 0 0-6-.4l-3 3a4 4 0 0 0 5.7 5.7l1.6-1.6' }]],
  Uso: [['path', { d: 'M3 3v16a2 2 0 0 0 2 2h16M18 17V9M13 17V5M8 17v-3' }]],
  Usuarios: [['circle', { cx: 9, cy: 7, r: 3 }], ['path', { d: 'M3 20v-2a6 6 0 0 1 12 0v2M17 4a3 3 0 0 1 0 6M18 13a4 4 0 0 1 3 4v3' }]],
  Calendario: [['rect', { x: 3, y: 5, width: 18, height: 16, rx: 2 }], ['path', { d: 'M7 3v4m10-4v4M3 10h18' }]],
  Apariencia: [['path', { d: 'M12 3a9 9 0 1 0 0 18c2 0 2-2 1-3s-1-3 1-3h3a4 4 0 0 0 4-4 9 9 0 0 0-9-8z' }], ['path', { d: 'M7 9h.1m3-3h.1m2 4h.1' }]],
  Ayuda: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M9 9a3 3 0 1 1 4 3c-1 .5-1 1-1 2m0 3h.01' }]],
  Actualizaciones: [['circle', { cx: 12, cy: 12, r: 9.5 }], ['path', { d: 'M12 7.5v8M8.5 12.5 12 16l3.5-3.5' }]]
};
var SVG_ENGRANE = [['path', { d: 'M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z' }], ['circle', { cx: 12, cy: 12, r: 3 }]];
function svgDe(piezas, tam) {
  var ns = 'http://www.w3.org/2000/svg', s = document.createElementNS(ns, 'svg');
  var base = { width: tam, height: tam, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
  for (var k in base) s.setAttribute(k, base[k]);
  piezas.forEach(function (p) { var n = document.createElementNS(ns, p[0]); for (var a in p[1]) n.setAttribute(a, p[1][a]); s.appendChild(n); });
  return s;
}
function svgEngrane() { return svgDe(SVG_ENGRANE, 23); }
var CFG_SEC = ['General', 'Motores', 'Conexiones', 'Permisos', 'Uso', 'Actualizaciones',
  'Usuarios', 'Calendario', 'Apariencia', 'Ayuda'];
function cfgGrupo(C, titulo, filas) { if (titulo) C.appendChild(el('div', 'cg', titulo)); var c = el('div', 'cc'); filas.forEach(function (f) { c.appendChild(f); }); C.appendChild(c); return c; }
function cfgFila(titulo, desc, ctrl) { var r = el('div', 'cr'), t = el('div', 't'); t.appendChild(el('b', null, titulo)); if (desc) t.appendChild(el('small', null, desc)); r.appendChild(t); if (ctrl) r.appendChild(ctrl); return r; }
function cfgSw(k, despues) {
  var b = el('button', 'sw' + (CFG_LOCAL.get(k) ? ' on' : '')); b.appendChild(el('i'));
  b.onclick = function (e) { e.stopPropagation(); var v = !CFG_LOCAL.get(k); CFG_LOCAL.set(k, v); b.classList.toggle('on', v); if (despues) despues(v); };
  return b;
}
/* el ajuste arquitectura.paquete (el mismo de `settings.py set`); si lo fija el entorno de la página, se dice */
function cfgSwPaquete(re) {
  var p = S.paquete || {}, b = el('button', 'sw' + (p.encendido ? ' on' : '')); b.appendChild(el('i'));
  if (p.entorno) { b.disabled = true; b.title = 'Lo fija WORKSPACE_PAQUETE=' + p.entorno + ' en el entorno de la página'; }
  b.onclick = function (e) {
    e.stopPropagation(); b.disabled = true;
    post('/api/v2/paquete', { encendido: !p.encendido }).then(function (d) {
      S.paquete = d; nota(d.guardado ? 'Encendido: se aplica al abrir cada motor' : 'Apagado: los motores abren como siempre'); if (re) re();
    }, function (e2) { nota(e2.message, true); b.disabled = false; });
  };
  return b;
}
/* Configuración → Permisos, por agente (decisión del dueño, 18-nov): dos opciones, «Automático» de fábrica. Se guarda
   en su agent.json (/api/v2/autonomia) y vale para su terminal y para la página. Las dos son modos oficiales de su
   motor: Workspace nunca se salta su seguridad. */
var NIVELES_PERMISO = [
  { v: 'auto', t: 'Automático (recomendado)', d: 'Usa el modo automático oficial de su motor: trabaja sin interrumpirte y te pregunta lo arriesgado.' },
  { v: 'preguntar', t: 'Preguntarme todo', d: 'Te pide permiso antes de editar o de correr algo.' }
];
var PERMISOS_SEGURIDAD = 'Workspace nunca se salta la seguridad de tu motor: solo elige cuál de sus modos oficiales usa.';
/* lo que es «Automático» en un motor sin modo automático oficial (su ficha: permisos.niveles.auto.no), en una línea:
   lo que de verdad hace su lanzador con «brain» (engines/*, control: su aviso) */
var SIN_AUTO = {
  codex: 'Codex no tiene modo automático oficial: edita en su carpeta sin preguntarte, dentro de su sandbox, y te pregunta cuando él lo decide.',
  hermes: 'Hermes no tiene modo automático oficial: te pide permiso para escribir archivos, pero corre comandos sin preguntarte, también fuera de su carpeta.',
  openclaw: 'OpenClaw no tiene modo automático oficial: escribe y corre comandos sin preguntarte, también fuera de su carpeta.'
};
function sinAuto(motor) { return SIN_AUTO[motor] || motorN(motor) + ' no tiene modo automático oficial: edita en su carpeta sin preguntarte y te pregunta lo demás.'; }
/* B02 (cacería 19-nov): donde la vía oficial de su motor no pregunta todo, «Preguntarme todo» no se ofrece y se dice
   por qué (pagina_v2.no_pregunta, de la capa de control) */
function noPregunta(p) { return p.no_pregunta || motorN(p.motor) + ' no puede preguntarte todo por su vía oficial.'; }
/* un nivel que la página ya no ofrece (se eligió en su terminal) se muestra con lo más cercano y no se reescribe hasta
   que elijas: «editar» (lo de antes) ≈ Automático; «sin_permisos» (sandbox) es de solo lectura aquí */
var EN_SU_CAJA = 'En su caja (sandbox del motor)';
function filaPermiso(p, re) {
  var a = ag(p.agente), nombre = a ? a.n : p.agente, m = motorN(p.motor);
  if (p.nivel === 'sin_permisos') {
    return cfgFila(nombre, m + ' trabaja dentro de su sandbox. Se eligió en su terminal; la página no lo cambia.', el('span', 'dd ro', EN_SU_CAJA));
  }
  var act = NIVELES_PERMISO.filter(function (n) { return n.v === p.nivel; })[0] || NIVELES_PERMISO[0];     // editar → Automático
  var dd = el('button', 'dd'); dd.appendChild(el('span', null, act.t)); dd.appendChild(svg('chev'));
  dd.onclick = function (e) {
    e.stopPropagation();
    pop(dd, NIVELES_PERMISO.map(function (n) {
      var no = n.v === 'preguntar' && !p.pregunta, sub = n.v === 'auto' && !p.auto ? sinAuto(p.motor) : no ? noPregunta(p) : '';
      return { t: n.t, sub: sub, off: no, ok: n.v === p.nivel, run: function () { cambiarPermiso(p, n, re); } };
    }));
  };
  var desc = m;
  if (p.nivel === 'editar') desc += ' · hoy edita en su carpeta sin preguntarte y te pregunta lo demás (un ajuste de antes). Elige una opción para cambiarlo.';
  else if (act.v === 'auto' && !p.auto) desc = sinAuto(p.motor);
  else if (act.v === 'preguntar' && !p.pregunta) desc = noPregunta(p) + ' Por eso no se ofrece: pásalo a Automático.';
  if (p.fijado) desc += ' ' + p.fijado;
  return cfgFila(nombre, desc, dd);
}
function cambiarPermiso(p, n, re) {
  if (n.v === p.nivel) return;
  post('/api/v2/autonomia', { agente: p.agente, nivel: n.v }).then(function (d) {
    p.nivel = n.v; nota(d.texto || n.t); if (re) re();
  }, function (e) { nota(e.message, true); });
}
var SECCION = {
  General: function (C, re) {
    C.appendChild(el('h2', null, 'General'));
    cfgGrupo(C, 'Al escribir', [cfgFila('Enviar con ⌘↵', 'Pulsa ⌘↵ (Ctrl+↵) para enviar tu mensaje. Enter hace una línea nueva.', cfgSw('cmdEnter', function (on) { nota(on ? 'Ahora envías con ⌘↵' : 'Ahora envías con Enter'); }))]);
    cfgGrupo(C, 'Arquitectura nueva', [cfgFila('Paquete por sesión', 'Abre cada motor con el paquete de Workspace (sus hooks, el MCP y las skills, por su vía oficial): la página ve su estado sin leer su pantalla. Se aplica al abrir cada motor.', cfgSwPaquete(re))]);
    var apa = el('button', 'btc rojo', 'Apagar'); apa.onclick = function () { apagar(); };
    cfgGrupo(C, 'La página', [cfgFila('Apagar la página', 'Se cierran los motores que abrió; tus agentes y su memoria quedan igual.', apa)]);
    cfgArchivados(C);                                              // los archivados, con «Traer de vuelta» (72_apartar.js)
  },
  Motores: function (C, re) {
    C.appendChild(el('h2', null, 'Motores'));
    C.appendChild(el('p', 'cs', 'Los programas que hacen el trabajo de tus agentes. Cada uno entra con su propia cuenta, en su terminal.'));
    cfgLineaConexiones(C);
    var listos = S.motores.filter(function (m) { return m.listo && m.sesion !== false; });
    var dd = el('button', 'dd'), def = motorPorDefecto();
    dd.appendChild(el('span', null, def ? motorN(def) : 'ninguno con sesión')); dd.appendChild(svg('chev'));
    dd.onclick = function (e) { e.stopPropagation(); pop(dd, listos.map(function (m) { return { t: m.nombre, ok: m.id === def, run: function () { CFG_LOCAL.set('motorDef', m.id); nota('Los agentes nuevos empiezan con ' + m.nombre); re(); } }; })); };
    cfgGrupo(C, null, [cfgFila('Motor por defecto', 'Con el que empiezan los agentes nuevos.', listos.length ? dd : null)]).style.marginTop = '20px';
    cfgMotores(C, re);
  },
  Usuarios: function (C, re) { cfgUsuarios(C, re); },
  Calendario: function (C, re) { cfgCalendario(C, re); },
  Apariencia: function (C, re) { cfgApariencia(C, re); },
  Ayuda: function (C) { cfgAyuda(C); },
  Conexiones: function (C, re) { conexiones(C, re); },
  Permisos: function (C, re) {
    C.appendChild(el('h2', null, 'Permisos'));
    C.appendChild(el('p', 'cs', 'Cuánto hacen tus agentes sin preguntarte. Lo que su motor pregunta llega al chat como tarjeta: Permitir · Siempre · No.'));
    cfgGrupo(C, 'Las opciones', NIVELES_PERMISO.map(function (n) { return cfgFila(n.t, n.d, null); }));
    C.appendChild(el('p', 'cs seg', PERMISOS_SEGURIDAD)).style.marginTop = '12px';
    var ps = S.permisos || [];
    if (ps.length) cfgGrupo(C, 'Tus agentes', ps.map(function (p) { return filaPermiso(p, re); })).style.marginTop = '20px';
    C.appendChild(el('p', 'cs', 'Vale para su terminal y para la página, desde su próxima sesión. Lo que fijaste a mano en la configuración de su motor gana.')).style.marginTop = '12px';
    var sp = S.sinPreguntar || {}, ids = S.motores.map(function (m) { return m.id; }).filter(function (id) { return sp[id]; });
    if (ids.length) cfgGrupo(C, 'Lo que hacen sin preguntar', ids.map(function (id) { return cfgFila(motorN(id), sp[id], null); })).style.marginTop = '20px';
  },
  Uso: function (C) {
    C.appendChild(el('h2', null, 'Uso'));
    C.appendChild(el('p', 'cs', 'Lo que cada motor informa por su vía oficial mientras trabaja desde aquí.'));
    var filas = S.motores.filter(function (m) { return m.listo; }).map(function (m) {
      var u = usoDelMotor(m.id), txt = u ? Object.keys(u).map(function (k) { return k + ': ' + u[k]; }).join(' · ') : 'Este motor no comparte cuánto llevas por esta vía.';
      return cfgFila(m.nombre, txt, null);
    });
    if (filas.length) cfgGrupo(C, null, filas).style.marginTop = '20px';
  },
  Actualizaciones: function (C) {
    C.appendChild(el('h2', null, 'Actualizaciones'));
    var r = cfgFila('Workspace', (S.version ? 'Versión ' + S.version + ' · ' : '') + 'Se actualiza desde el hub o con `workspace update`.', null);
    cfgGrupo(C, null, [r]).style.marginTop = '20px';
  }
};
/* la versión de un motor en una línea: /api/sistema/motores la manda como {estado, instalada, texto, nota}
   (localhost_sistema: su `texto` ya dice «0.169.0 · probada», «… · nueva»…); sin texto, la instalada; un texto suelto,
   tal cual. Nunca «[object Object]» */
function versionMotor(v) {
  if (v == null || v === '') return '';
  if (typeof v !== 'object') return String(v);
  return String(v.texto || v.instalada || '');
}
function usoDelMotor(motor) {
  var u = null;
  S.agentes.forEach(function (a) { var s = (S.usoSnap[a.id] || {}).uso; if (s && Object.keys(s).length && (fotoDe(a).motor || a.motor) === motor) u = s; });
  return u;
}
function configuracion(sec) {
  cerrarCapas(); quitarTip();
  var SEC = sec || 'General', v = el('div', 'velo'), md = el('div', 'cfg'); v.appendChild(md);
  var nav = el('nav'), cuerpo = el('div', 'cuerpo'); md.appendChild(nav); md.appendChild(cuerpo);
  var x = el('button', 'cb cx'); x.appendChild(icono('x')); x.title = 'Cerrar'; x.onclick = function () { v.remove(); }; md.appendChild(x);
  function navPinta() {
    nav.textContent = '';
    CFG_SEC.forEach(function (s2) { var b = el('button', s2 === SEC ? 'on' : ''); b.appendChild(svgDe(SVG_CFG[s2], 19)); b.appendChild(el('span', null, s2)); b.onclick = function () { if (SEC === s2) return; SEC = s2; navPinta(); pinta(); }; nav.appendChild(b); });
  }
  function pinta() {
    var sc = cuerpo.scrollTop, actual = SEC;
    cuerpo.textContent = ''; cuerpo.dataset.sec = actual;
    SECCION[actual](cuerpo, function () { if (v.isConnected && SEC === actual) pinta(); });
    cuerpo.scrollTop = sc;
  }
  v.onclick = function (e) { if (e.target === v) v.remove(); };
  document.body.appendChild(v); navPinta(); pinta();
  api('/api/v2/info').then(function (d) {
    S.version = d.version || ''; S.sinPreguntar = d.sin_preguntar || {}; S.paquete = d.paquete || {}; S.permisos = d.permisos || [];
    if (v.isConnected && ['General', 'Permisos', 'Actualizaciones'].indexOf(SEC) >= 0) pinta();
  }, function () {});
}
