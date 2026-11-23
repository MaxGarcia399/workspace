function cfgBoton(texto, accion) {
  var b = el('button', 'btc', texto);
  b.type = 'button';
  b.onclick = accion;
  return b;
}
function cfgConsulta(ruta, params) {
  return api(ruta + '?' + new URLSearchParams(params));
}
function cfgAccion(b, trabajo, hecho) {
  if (b.disabled) return;
  b.disabled = true;
  trabajo().then(hecho).catch(function (e) {
    nota(e.message, true);
  }).finally(function () { b.disabled = false; });
}
function cfgEstado(C, texto) { return C.appendChild(el('p', 'cs', texto)); }
function cfgGrande(b) { b.classList.add('grande'); return b; }
/* H3-b + Conexiones en verde (F5): Motores dice en UNA línea cómo están las Conexiones de Workspace (el chequeo rápido,
   GET /api/v2/chequeo: ✓ todo responde · hace … · ⚠ N cosas por hacer · ✗ N rotas) y lleva a Configuración →
   Conexiones, donde vive lo de adentro. Debajo, la revisión al abrir: el motor que se actualizó («Copilot se
   actualizó a 1.0.114 · revisado al abrir: contesta y lo de Workspace sigue en su lugar»). No depende de que
   Conexiones esté cargada. */
function cfgCxLinea(d) {
  var rotas = 0, tuyas = 0;
  if (d && d.workspace && d.workspace.estado === 'roto') rotas++;
  ((d && d.motores) || []).forEach(function (m) {
    (m.filas || []).forEach(function (f) { if (f.estado === 'roto') rotas++; else if (f.estado === 'tuyo') tuyas++; });
  });
  if (!d || (!d.workspace && !(d.motores || []).length)) return ['', 'revisando…'];
  if (rotas) return ['mal', '✗ ' + rotas + (rotas === 1 ? ' rota' : ' rotas')];
  if (tuyas) return ['warn', '⚠ ' + tuyas + (tuyas === 1 ? ' cosa por hacer' : ' cosas por hacer')];
  return ['ok', '✓ todo responde' + (d.hace ? ' · ' + d.hace : '')];
}
function cfgLineaConexiones(C) {
  var fila = C.appendChild(el('div', 'cfg-cxl')), t = el('span', 'cxe', 'revisando…');
  fila.appendChild(el('b', null, 'Conexiones de Workspace'));
  fila.appendChild(t);
  var ir = cfgBoton('Ver en Conexiones ›', function (e) { if (e) e.stopPropagation(); var v = document.querySelector('.velo'); if (v) v.remove(); configuracion('Conexiones'); });
  fila.appendChild(ir);
  var cambios = C.appendChild(el('div', 'cfg-cambios'));
  function pinta(d) {
    var x = cfgCxLinea(d);
    t.textContent = x[1];
    t.className = 'cxe ' + x[0];
    cambios.textContent = '';
    ((d && d.motores) || []).forEach(function (m) {
      if (!m.cambio) return;
      cambios.appendChild(el('p', 'cfg-cambio ' + (m.cambio.estado === 'ok' ? 'bien' : 'mal'), (m.cambio.estado === 'ok' ? '↑ ' : '') + m.cambio.texto));
    });
  }
  var cx = typeof CX !== 'undefined' ? CX : null;
  if (cx && cx.d) pinta(cx.d);
  try {          /* (la línea nunca tumba a Motores: si no se pudo pedir, dice «revisando…») */
    api('/api/v2/chequeo').then(function (d) { if (cx) { cx.d = d; cx.t = Date.now(); } if (fila.isConnected) pinta(d); }, function () { if (fila.isConnected) pinta(null); });
  } catch (_) { pinta(null); }
}

var CFG_MOTOR_ACCION = {
  cuenta: 'Cuenta y proveedor', iniciar_sesion: 'Iniciar sesión', verificar: 'Verificar',
  actualizar: 'Actualizar', reinstalar: 'Reinstalar', reparar: 'Reparar', instalar: 'Instalar'
};
function cfgMotores(C, re) {
  var zona = C.appendChild(el('div')), carga = cfgEstado(zona, 'Cargando motores…');
  api('/api/sistema/motores').then(function (d) {
    if (!zona.isConnected) return;
    zona.textContent = '';
    cfgGrupo(zona, null, [cfgFila('Inventario', '', cfgBoton('Volver a detectar', function () {
      var b = this;
      cfgAccion(b, function () { return post('/api/sistema/motores/recargar', {}); }, re);
    }))]);
    (d.motores || []).forEach(function (m) { cfgFichaMotor(zona, m, re); });
  }).catch(function (e) { carga.textContent = e.message; });
}
function cfgFichaMotor(C, m, re) {
  var version = versionMotor(m.version);
  var datos = [m.estado_texto, m.sesion_texto, version && 'Versión ' + version,
    m.integracion && m.integracion.texto].filter(Boolean);
  var card = cfgGrupo(C, null, [cfgFila(m.nombre, datos.join(' · '))]);
  card.classList.add('cfg-ficha');
  if (m.agentes.length) cfgEstado(card, 'Lo usan ' + m.agentes.join(', '));
  if (m.bloqueo) cfgEstado(card, m.bloqueo);
  if (m.falta.length) cfgEstado(card, 'Falta ' + m.falta.join(', '));
  var acciones = card.appendChild(el('div', 'cfg-acciones'));
  var zona = card.appendChild(el('div', 'cfg-flujo'));
  var bloqueado = m.estado === 'bloqueado';
  if (m.instalado && !bloqueado) {             /* H3-b: lo principal, en botones grandes */
    acciones.appendChild(cfgGrande(cfgBoton('Cuenta y proveedor', function () { cfgCuentaMotor(zona, m, re, false); })));
    if (m.login) acciones.appendChild(cfgGrande(cfgBoton('Iniciar sesión', function () { cfgFlujoMotor(zona, m, 'iniciar_sesion', '', re); })));
    acciones.appendChild(cfgGrande(cfgBoton('Modelo', function () { cfgCuentaMotor(zona, m, re, true); })));
  }
  if (m.instalado) {
    acciones.appendChild(cfgBoton('Verificar', function () {
      cfgAccion(this, function () { return post('/api/sistema/motor/verificar', { motor: m.id }); }, function (r) {
        nota(r.mensaje || 'Verificando…');
        setTimeout(function () { if (card.isConnected) re(); }, 1600);
      });
    }));
    var hub = el('input'); hub.type = 'checkbox'; hub.checked = m.en_hub;
    var etiqueta = el('label', 'cfg-casilla'); etiqueta.appendChild(hub);
    etiqueta.appendChild(document.createTextNode(' Ofrecer en el hub')); acciones.appendChild(etiqueta);
    hub.onchange = function () {
      hub.disabled = true;
      post('/api/sistema/motor/hub', { motor: m.id, encendido: hub.checked })
        .catch(function (e) { hub.checked = !hub.checked; nota(e.message, true); })
        .finally(function () { hub.disabled = false; });
    };
  }
  var mantenimiento = ['instalar', 'reinstalar', 'reparar'].indexOf(m.siguiente) >= 0 ? m.siguiente :
    m.instalado && m.receta && !bloqueado ? 'actualizar' : '';
  if (mantenimiento) acciones.appendChild(cfgBoton(CFG_MOTOR_ACCION[mantenimiento], function () {
    cfgFlujoMotor(zona, m, mantenimiento, '', re);
  }));
  if (!m.instalado && !mantenimiento) cfgEstado(card, 'Instálalo por su vía oficial para configurar la cuenta.');
}
function cfgZonaMotor(zona, titulo) {
  zona.textContent = '';
  zona.appendChild(cfgFila(titulo, '', cfgBoton('Cerrar', function () { zona.textContent = ''; })));
  return zona.appendChild(el('div', 'cfg-flujo-cuerpo'));
}
function cfgCuentaMotor(zona, m, re, modelo) {
  var bloque = cfgZonaMotor(zona, modelo ? 'Modelo' : 'Cuenta y proveedor');
  var estado = cfgEstado(bloque, 'Consultando la configuración oficial…');
  cfgConsulta('/api/sistema/motor/cuenta', { motor: m.id }).then(function (r) {
    if (!bloque.isConnected) return;
    if (!r.menu) return cfgFlujoMotor(zona, m, 'cuenta', '', re);
    var opciones = r.acciones || [];
    var modelos = opciones.filter(function (a) { return a.clave === 'models'; });
    if (modelo && modelos.length === 1) return cfgFlujoMotor(zona, m, 'cuenta', modelos[0].clave, re);
    estado.remove();
    if (r.nota) cfgEstado(bloque, r.nota);
    if (r.aviso) cfgEstado(bloque, r.aviso);
    if (modelo) cfgEstado(bloque, 'Elige cómo abrir el selector en el motor.');
    var acciones = bloque.appendChild(el('div', 'cfg-acciones'));
    opciones.forEach(function (a) {
      acciones.appendChild(cfgBoton(a.etiqueta, function () { cfgFlujoMotor(zona, m, 'cuenta', a.clave, re); }));
    });
  }).catch(function (e) { estado.textContent = e.message; });
}
function cfgFlujoMotor(zona, m, accion, opcion, re) {
  var bloque = cfgZonaMotor(zona, CFG_MOTOR_ACCION[accion] + ' · ' + m.nombre);
  var estado = cfgEstado(bloque, 'Preparando el flujo oficial…');
  var datos = { motor: m.id, accion: accion, opcion: opcion };
  cfgConsulta('/api/sistema/motor/preparar', datos).then(function (p) {
    if (!bloque.isConnected) return;
    estado.remove();
    bloque.appendChild(el('pre', 'cfg-comando', (p.comandos || []).join('\n')));
    [p.fuente, p.aviso, p.nota].filter(Boolean).forEach(function (t) { cfgEstado(bloque, t); });
    bloque.appendChild(cfgBoton(p.confirmar ? 'Confirmar' : 'Abrir', function () {
      cfgAccion(this, function () {
        return post('/api/sistema/motor/correr', Object.assign({}, datos, { confirmado: !!p.confirmar }));
      }, function (r) { if (bloque.isConnected) cfgTareaMotor(zona, m, r.tarea, re); });
    }));
  }).catch(function (e) { estado.textContent = e.message; });
}
function cfgTareaMotor(zona, m, tarea, re) {
  var bloque = cfgZonaMotor(zona, m.nombre);
  var estado = cfgEstado(bloque, 'Abriendo la herramienta oficial…');
  var acciones = bloque.appendChild(el('div', 'cfg-acciones'));
  var cerrar = cfgBoton('Cerrar tarea', function () {
    cfgAccion(this, function () { return post('/api/sistema/motor/tarea/cerrar', { tarea: tarea }); }, re);
  });
  cerrar.hidden = true; acciones.appendChild(cerrar);
  function tick() {
    if (!bloque.isConnected) return;
    cfgConsulta('/api/sistema/motor/tarea', { tarea: tarea, resumen: '1' }).then(function (t) {
      if (!bloque.isConnected) return;
      var vivo = t.estado === 'abriendo' || t.estado === 'corriendo';
      estado.textContent = t.mensaje || (vivo ? 'Continúa en la pestaña oficial de tu terminal' + (t.etiqueta ? ' · ' + t.etiqueta : '.') : 'La tarea terminó.');
      cerrar.hidden = !t.abierta;
      if (vivo) setTimeout(tick, 1200);
      else acciones.appendChild(cfgBoton('Volver a la ficha', re));
    }).catch(function (e) { estado.textContent = e.message; });
  }
  tick();
}

function cfgEntrada(label, valor) {
  var input = el('input', 'cfg-input');
  input.setAttribute('aria-label', label); input.placeholder = label; input.value = valor || ''; input.maxLength = 40;
  return input;
}
function cfgUsuarios(C, re) {
  C.appendChild(el('h2', null, 'Usuarios'));
  var estado = cfgEstado(C, 'Cargando quién usa cada agente…');
  api('/api/sistema/usuarios').then(function (d) {
    if (!estado.isConnected) return;
    estado.remove();
    (d.agentes || []).forEach(function (a) { cfgUsuariosAgente(C, a, re); });
    if (!(d.agentes || []).length) cfgEstado(C, 'Aún no hay agentes.');
  }).catch(function (e) { estado.textContent = e.message; });
}
var CFG_USUARIO_ACCION = {
  crear: '/api/sistema/usuario/crear', renombrar: '/api/sistema/usuario/renombrar',
  unir: '/api/sistema/usuario/unir', soy: '/api/sistema/usuario/soy'
};
function cfgUsuariosAgente(C, a, re) {
  var grupo = cfgGrupo(C, a.nombre || a.agente, []);
  function operacion(b, ruta, datos) {
    cfgAccion(b, function () {
      return post(CFG_USUARIO_ACCION[ruta], Object.assign({ agente: a.agente }, datos));
    }, function (r) { if (r.mensaje) nota(r.mensaje); if (grupo.isConnected) re(); });
  }
  if (a.error) cfgEstado(grupo, 'No se pudieron leer los usuarios de este agente.');
  a.usuarios.forEach(function (u) {
    var acciones = el('div', 'cfg-acciones');
    var alias = (u.alias || []).join(', ');
    grupo.appendChild(cfgFila(u.nombre + (u.yo ? ' · tú' : ''), u.pestanas + ' pestañas' + (alias ? ' · ' + alias : ''), acciones));
    if (!u.yo && u.opciones.indexOf('soy_yo') >= 0) acciones.appendChild(cfgBoton('Soy yo', function () {
      operacion(this, 'soy', { usuario: u.nombre });
    }));
    if (u.opciones.indexOf('renombrar') >= 0) {
      var nombre = cfgEntrada('Nombre nuevo', u.nombre);
      acciones.appendChild(nombre);
      acciones.appendChild(cfgBoton('Renombrar', function () {
        var v = nombre.value.trim();
        if (v && v !== u.nombre) operacion(this, 'renombrar', { usuario: u.nombre, nuevo: v, revision: u.revision });
      }));
    }
    if (u.opciones.indexOf('unir') >= 0) {
      var destinos = el('select', 'cfg-input'); destinos.setAttribute('aria-label', 'Usuario de destino');
      destinos.appendChild(el('option', '', 'Elegir destino'));
      destinos.firstChild.value = '';
      a.usuarios.filter(function (v) { return v.id !== u.id; }).forEach(function (v) {
        var o = el('option', '', v.nombre); o.value = v.nombre; destinos.appendChild(o);
      });
      acciones.appendChild(destinos);
      acciones.appendChild(cfgBoton('Unir', function () {
        if (!destinos.value) return destinos.focus();
        if (window.confirm('¿Unir ' + u.nombre + ' con ' + destinos.value + '?')) {
          operacion(this, 'unir', { origen: u.nombre, destino: destinos.value });
        }
      }));
    }
  });
  var nuevo = cfgEntrada('Nombre del usuario');
  var controles = el('div', 'cfg-acciones'); controles.appendChild(nuevo);
  controles.appendChild(cfgBoton('Crear usuario', function () {
    var nombre = nuevo.value.trim(); if (!nombre) return nuevo.focus();
    operacion(this, 'crear', { nombre: nombre });
  }));
  grupo.appendChild(cfgFila('Usuario nuevo', '', controles));
}

var CFG_SEMANA = 0;
function cfgCalendario(C, re) {
  C.appendChild(el('h2', null, 'Calendario'));
  var lunes = new Date();
  lunes.setHours(12, 0, 0, 0);
  lunes.setDate(lunes.getDate() - (lunes.getDay() + 6) % 7 + 7 * CFG_SEMANA);
  var controles = C.appendChild(el('div', 'cfg-acciones'));
  [['Semana anterior', -1], ['Hoy', 0], ['Semana siguiente', 1]].forEach(function (op) {
    controles.appendChild(cfgBoton(op[0], function () {
      CFG_SEMANA = op[1] === 0 ? 0 : CFG_SEMANA + op[1]; re();
    }));
  });
  var lista = C.appendChild(el('div')), estado = cfgEstado(lista, 'Cargando eventos…');
  var formato = new Intl.DateTimeFormat('es', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  api('/api/calendario').then(function (d) {
    if (!lista.isConnected) return;
    estado.remove();
    var eventos = (d.eventos || []).slice().sort(function (a, b) { return (a.time || '').localeCompare(b.time || ''); });
    for (var i = 0; i < 7; i++) {
      var dia = new Date(lunes); dia.setDate(lunes.getDate() + i);
      var iso = [dia.getFullYear(), String(dia.getMonth() + 1).padStart(2, '0'), String(dia.getDate()).padStart(2, '0')].join('-');
      var filas = eventos.filter(function (e) { return e.date === iso; }).map(function (e) {
        return cfgFila(e.title, [e.time || 'Todo el día', e.cat, e.done ? 'Hecho' : ''].filter(Boolean).join(' · '));
      });
      cfgGrupo(lista, formato.format(dia), filas.length ? filas : [cfgFila('Sin eventos')]);
    }
  }).catch(function (e) { estado.textContent = e.message; });
}

function cfgAyuda(C) {
  C.appendChild(el('h2', null, 'Ayuda'));
  cfgGrupo(C, 'Teclas de la página', [
    cfgFila(CFG_LOCAL.get('cmdEnter') ? '⌘ / Ctrl + Enter' : 'Enter', 'Enviar un mensaje'),
    cfgFila('Shift + Enter', 'Insertar un salto de línea'), cfgFila('Esc', 'Cerrar el panel o diálogo')
  ]);
  cfgGrupo(C, 'Comandos del hub y la terminal', [
    cfgFila('workspace --help', 'Ver los comandos disponibles'),
    cfgFila('workspace doctor', 'Revisar instalación, motores y conexiones'),
    cfgFila('workspace update', 'Actualizar Workspace'),
    cfgFila('/model y /effort', 'Abrir los ajustes compatibles del motor desde el chat')
  ]);
  cfgGrupo(C, 'La guía', [
    cfgFila('Ver la guía otra vez', 'El recorrido de cinco pasos por la página. Sale sola una vez; aquí, cuando quieras.',
      cfgBoton('Ver', function (e) { if (e) e.stopPropagation(); var v = document.querySelector('.velo'); if (v) v.remove(); guia(); }))
  ]);
  var guias = [['primer-arranque', 'Primer arranque'], ['hub', 'Hub y teclas'], ['motores', 'Motores y proveedores'],
    ['actualizaciones', 'Actualizaciones'], ['privacidad', 'Privacidad']];
  cfgGrupo(C, 'Documentación', guias.map(function (g) {
    var enlace = el('a', 'btc', 'Leer');
    enlace.href = '/manual/es/' + g[0] + '.md'; enlace.target = '_blank'; enlace.rel = 'noopener';
    enlace.setAttribute('aria-label', 'Leer ' + g[1]);
    return cfgFila(g[1], '', enlace);
  }));
}

function cfgTemaGuardado() {
  var g = CFG_LOCAL.get('tema');
  return g && typeof g === 'object' && !Array.isArray(g) ? Object.assign({}, g) : {};
}
function cfgTemaActivo() {
  var g = cfgTemaGuardado();
  if (CFG_LOCAL.get('temaPredeterminado') || !g.p) return null;
  return THEMES.find(function (t) { return +g.p === t[1] && +g.k === t[2] && +g.x === t[3]; }) || null;
}
function cfgAplicarTema(t) {
  var raiz = typeof document === 'undefined' ? null : document.documentElement;
  if (!raiz || !raiz.classList) return;
  if (t === undefined) t = cfgTemaActivo();
  raiz.classList.toggle('cfg-tema', !!t);
  if (!t) return;
  var fondo = COL.P[t[1] - 1], tinta = COL.K[t[2] - 1], acento = COL.X[t[3] - 1];
  var luz = fondo.slice(1).match(/../g).map(function (v) {
    var c = parseInt(v, 16) / 255;
    return c <= .04045 ? c / 12.92 : Math.pow((c + .055) / 1.055, 2.4);
  });
  var claro = .2126 * luz[0] + .7152 * luz[1] + .0722 * luz[2] > .179;
  raiz.style.setProperty('--tema-fondo', fondo);
  raiz.style.setProperty('--tema-tinta', claro ? tinta : '#f4f3f7');
  raiz.style.setProperty('--tema-acento', acento);
}
function cfgApariencia(C, re) {
  C.appendChild(el('h2', null, 'Apariencia'));
  var actual = cfgTemaActivo(), opciones = C.appendChild(el('div', 'cfg-temas'));
  function elegir(t) {
    CFG_LOCAL.set('temaPredeterminado', !t);
    if (t) {
      var g = cfgTemaGuardado();
      g.p = String(t[1]); g.k = String(t[2]); g.x = String(t[3]); g.ver = '2';
      CFG_LOCAL.set('tema', g);
    }
    cfgAplicarTema(t); re();
  }
  [null].concat(THEMES).forEach(function (t) {
    var b = cfgBoton(t ? t[0] : 'Predeterminado', function () { elegir(t); });
    b.setAttribute('aria-pressed', String(t === actual));
    var muestra = el('span', 'cfg-muestra');
    var colores = t ? [COL.P[t[1] - 1], COL.K[t[2] - 1], COL.X[t[3] - 1]] : ['#141416', '#ededf0', '#a4a4ad'];
    colores.forEach(function (color) { var i = el('i'); i.style.background = color; muestra.appendChild(i); });
    b.prepend(muestra); opciones.appendChild(b);
  });
}
cfgAplicarTema();
