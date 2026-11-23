/* ================= datos: la API del servidor local y el estado de la página =================
   Un agente = una conversación (su pestaña de chat). Todo lo que se ve sale de /api/*; lo único que vive solo
   en la página es lo que todavía no llega del servidor (un mensaje recién enviado, una skill por arrancar).
   Arquitectura nueva (F3): la página es una VISTA del núcleo. Su estado en vivo y su conversación salen de
   /api/v2/* (el registro de eventos y el historial por eventos) y escribe por la capa de control: nunca lee la
   pantalla de un motor ni teclea en su terminal. */
var S = {
  agentes: [], act: null, formas: [], colores: [],
  vivo: {}, ejec: {}, pestanas: {}, conv: {}, pant: {}, skills: [], motores: [], usoSnap: {},
  /* H4-a: la pestaña que ves de cada agente (sin ella, ⌂), la foto entera de cada agente tal como llega (con su tira y
     la de cada pestaña) y la conversación de cada pestaña ya leída */
  tab: {}, vivoCrudo: {}, convs: {}, tabPend: {},
  local: {}, PANEL: '', PTAB: 'Resumen', EDIT: null, SKQ: '', RENOMBRA: '', caida: false
};
function api(ruta) {
  return fetch(ruta, { credentials: 'same-origin' }).then(respuesta);
}
/* `senal`: la de un AbortController, para cortar la espera (mandar corta al minuto: F3d) */
/* H4-a: lo que se le hace a una conversación va a la pestaña que ves de ese agente (sin `tab`, la de siempre) */
var CON_TAB = { '/api/v2/mandar': 1, '/api/v2/permiso': 1, '/api/v2/parar': 1, '/api/v2/quitar': 1, '/api/v2/responder': 1,
  '/api/v2/motor': 1, '/api/v2/terminal': 1, '/api/v2/terminal/cerrar': 1 };
function conTab(ruta, cuerpo) {
  if (!CON_TAB[ruta] || !cuerpo || !cuerpo.agente || cuerpo.tab !== undefined) return cuerpo;
  var x = ag(cuerpo.agente), t = x ? tabDe(x) : NAV;
  return t === NAV ? cuerpo : Object.assign({}, cuerpo, { tab: t });
}
function post(ruta, cuerpo, senal) {
  if (typeof conTab === 'function') cuerpo = conTab(ruta, cuerpo);
  var op = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo || {}) };
  if (senal) op.signal = senal;
  return fetch(ruta, op).then(respuesta);
}
/* La página que sirve es de antes de una actualización y no trae esa ruta («ruta desconocida»): en su lugar, una línea
   amable (el hub la renueva en cuanto queda libre). 503: atiende a muchas ventanas a la vez (`reintenta` s). */
var ACTUALIZANDO = 'Workspace se está actualizando… vuelve a intentar en unos segundos.';
function respuesta(r) {
  return r.text().then(function (t) {
    var j = {}; try { j = t ? JSON.parse(t) : {}; } catch (_) { j = {}; }
    if (!r.ok) {
      var sinRuta = r.status === 404 && /^ruta desconocida/.test(String(j.__err || ''));
      var e = new Error(sinRuta ? ACTUALIZANDO : (j.__err || ('Error ' + r.status)));
      e.status = r.status; e.datos = j; e.actualizando = sinRuta; e.ocupado = r.status === 503;
      if (e.ocupado) marcarConectado(true);
      throw e;
    }
    marcarConectado(true); return j;
  }, function (e) { throw e; });
}
function marcarConectado(ok) {
  if (ok === !S.caida) return; S.caida = !ok;
  var c = $('#caida'); if (c) c.remove();
  if (!ok) { c = el('div', 'caida', 'Se perdió la conexión con Workspace; reintentando…'); c.id = 'caida'; document.body.appendChild(c); }
}
function ag(id) { return S.agentes.filter(function (a) { return a.id === id; })[0]; }
function activo() { return ag(S.act); }
/* lo de esta vista de cada conversación (lo escrito, lo que mandaste y aún no llega…): por agente y pestaña (`t`: la
   de una pestaña dada; sin ella, la que ves) */
function L(a, t) { if (t === undefined) t = tabDe(a); var k = t === NAV ? a.id : a.id + '|' + t; return S.local[k] || (S.local[k] = {}); }
function motorN(id) { var m = S.motores.filter(function (x) { return x.id === id; })[0]; return m ? m.nombre : (id || 'sin motor'); }
function skillsDe(a) { return S.skills.filter(function (s) { return s.agente === a.id; }); }

/* ---------- la conversación del agente: UNA y fija («navegador»), la misma con cualquier motor ----------
   El servidor la crea con el primer mensaje y la saca de los menús del hub y de la terminal. */
var NAV = 'navegador';
function pestanaDe(a, slug) { return (S.pestanas[a.id] || []).filter(function (p) { return p.slug === slug; })[0]; }
/* H4-a: la conversación que ves es la de su pestaña (una de sus sesiones) o la de siempre */
function slugChat(a) { var t = tabDe(a); if (t !== NAV) return t; return fotoDe(a).existe || pestanaDe(a, NAV) ? NAV : null; }

/* ---------- H4-a: las pestañas de cada agente (las guarda Workspace: las mismas en el hub y aquí) ---------- */
function tiraDe(a) { var f = (S.vivoCrudo || {})[a.id] || {}; return f.tabs && f.tabs.length ? f.tabs : [{ slug: NAV, nombre: 'Conversación', tipo: NAV }]; }
function tabDe(a) {
  var t = (S.tab || {})[a.id];
  if (!t || t === NAV) return NAV;
  var pe = (S.tabPend || {})[a.id];
  if (tiraDe(a).some(function (x) { return x.slug === t; }) || (pe && pe.slug === t && Date.now() - pe.t < 15000)) return t;
  return NAV;
}
function tabActual(a) { var t = tabDe(a); return tiraDe(a).filter(function (x) { return x.slug === t; })[0] || { slug: t, nombre: t, tipo: t === NAV ? NAV : 'sesion' }; }
/* la foto de lo que ves: la de su pestaña, con lo que es del agente (su perfil, sus pendientes); las skills son de ⌂ */
function fotoEfectiva(f, t) {
  if (!f || t === NAV) return f;
  var x = (f.tab_fotos || {})[t];
  if (!x) x = { estado: 'libre', existe: true, viva: false, cola: [], motor: '', tab: t, conv: '' };
  return Object.assign({}, x, { perfil: f.perfil, pend: f.pend, sesiones: f.sesiones, tabs: f.tabs, tab_fotos: f.tab_fotos,
    ejecuciones: [], skill_vigente: '', revision: null });
}
function ponerFoto(id, f) {
  (S.vivoCrudo || (S.vivoCrudo = {}))[id] = f;
  var x = ag(id), e = x ? fotoEfectiva(f, tabDe(x)) : f;
  S.vivo[id] = e; S.pant[id] = e && e.viva ? e : null;
  return e;
}
function chatAbierto(a) { var f = S.vivo[a.id], p = pestanaDe(a, NAV); return f ? !!f.viva : !!(p && p.abierta); }
/* el motor con el que hablas AHORA: el de su conversación (cerrada: con el que iba; puede no ser el de las nuevas) */
function motorChat(a) {
  /* mientras cambia de motor, el de antes: el chip, el uso y el panel se repintan cuando el cambio TERMINA */
  var cm = cambioDe(a); if (cm && cm.de && cm.paso !== 'listo' && !(cm.paso === 'error' && fotoDe(a).viva)) return cm.de;
  var p = S.pant[a.id], c = S.conv[a.id], s = slugChat(a), pe = s && pestanaDe(a, s); return (p && p.motor) || (c && c.motor) || (pe && pe.motor) || a.motor;
}
/* al reabrirla, sigue con el motor con que iba (si todavía está listo); si no, el del agente */
function motorAbrir(a) { var c = S.conv[a.id], m = c && c.motor; return m && S.motores.some(function (x) { return x.id === m && x.listo; }) ? m : ''; }

/* ---------- qué está haciendo cada agente: lo dice el SERVIDOR (front_vivo), la página lo pinta ----------
   Su foto trae el estado con nombre (dormido · libre · enviando → recibido → trabajando → terminó / esperándote /
   error / cambiando) y desde cuándo. Lo único que se pone aquí es lo que el servidor todavía no sabe: lo que acabas
   de mandar (enviando) y la skill que activaste y aún no arranca. */
function fotoDe(a) { return S.vivo[a.id] || {}; }
function detenida(a, e) { return (L(a).detenidas || {})[e.id] || (a.detenidas || []).indexOf(e.id) >= 0; }
/* skills-cierre · «la skill que corre» tiene UNA regla, la del servidor (pagina_v2._vigente): su foto la trae como
   `skill_vigente` (y /api/ejecuciones como `vigente`). Aquí solo se le quita lo que acabas de detener (aún no llega).
   `pausada` (se detuvo sin terminar) y `listo` no bloquean. */
var ABIERTA = { arrancando: 1, corriendo: 1, pide: 1 };
function vigenteDelServidor(a) {
  var f = S.vivo[a.id]; if (f && 'skill_vigente' in f) return f.skill_vigente || '';
  return a.id in (S.vig || {}) ? S.vig[a.id] || '' : null;
}
function ejecVigente(a) {
  var lista = S.ejec[a.id] || [], id = vigenteDelServidor(a);
  if (id !== null) return lista.filter(function (e) { return e.id === id && ABIERTA[e.estado] && !detenida(a, e); })[0] || null;
  return lista.filter(function (e) {
    if (detenida(a, e) || !ABIERTA[e.estado]) return false;
    var t = Date.parse(e.actualizado || e.creado || '') || 0;
    if (e.estado === 'arrancando' && t && Date.now() - t > 10 * 60000) return false;   // nunca arrancó: no bloquea
    return !t || Date.now() - t < 6 * 3600 * 1000;
  })[0] || null;
}
function pasosHechos(e) { return (e.pasos || []).filter(function (p) { return p.estado === 'done'; }).length; }
/* reverificación 19-nov (Cursor): una skill sin plan cuyo turno YA terminó no arrancó (su plan no quedó anotado: le
   dijiste que no, o falló). No se queda «Pensando…» en el chat: su motor está libre desde después de que empezó. */
function sinArrancar(f, e, desde) {
  var t = Date.parse(e.creado || e.actualizado || '') || 0;
  return !!t && !!desde && desde > t && /^(libre|termino|dormido|cerrado|error|no_salio)$/.test(f.estado || '');
}
var FESTEJO_MS = 6000;     // «terminó» se ve así un momento; luego, libre
function actividadDe(a) {
  var l = L(a), f = fotoDe(a), desde = (f.desde || 0) * 1000;
  if (l.skillPend) return { k: 'espera', s: l.skillPend.skill };
  if (f.estado === 'cambiando') return { k: 'cambiando' };
  var e = ejecVigente(a);
  if (e) {
    if (e.estado === 'pide') return { k: 'espera', s: e.skill };
    var n = (e.pasos || []).length;
    if (n) return { k: 'skill', n: n, p: Math.min(n - 1, pasosHechos(e)), s: e.skill };
    if (!sinArrancar(f, e, desde)) return { k: 'pensando', s: e.skill };
  }
  if (l.enviando || (l.pendiente && desde < l.pendiente.ts && !/^(trabajando|esperandote|error)$/.test(f.estado || ''))) return { k: 'enviando' };
  if (f.estado === 'cerrado' || (f.estado === 'no_salio' && !noSalioCerrado(a))) return { k: f.estado };
  if (f.estado === 'esperandote') return { k: 'espera' };
  if (f.estado === 'error' && errorDe(a)) return { k: 'error' };
  if (f.estado === 'trabajando') return { k: ultimoEsMio(a) ? 'pensando' : 'escribiendo' };
  if (f.estado === 'enviando' || f.estado === 'recibido') return { k: f.estado };
  if (f.estado === 'termino' && Date.now() - desde < FESTEJO_MS) return { k: 'listo' };
  return { k: f.viva ? 'libre' : 'dormido' };
}
/* el error que su motor enseña ahora (sin crédito, límite, sesión vencida…), si no lo cerraste */
function errorDe(a) {
  var e = fotoDe(a).error;
  if (!e || (L(a).errCerrado === e.texto)) return null;
  return e;
}
/* ocupado: lo que lo interrumpe se bloquea en el servidor (409); aquí solo se refleja con su razón en una línea */
var RAZON_OCUPADO = { trabajando: ' está trabajando · se libera al terminar', cambiando: ' está cambiando de motor · se libera al quedar listo',
  enviando: ' espera a que su motor acepte tu mensaje · se libera en un momento', recibido: ' espera a que su motor acepte tu mensaje · se libera en un momento' };
function ocupadoDe(a) {
  var f = fotoDe(a), e = f.estado;
  if (e === 'cambiando' && f.cambio && f.cambio.reabre) return a.n + ' se está reabriendo · se libera al quedar listo';
  return RAZON_OCUPADO[e] ? a.n + RAZON_OCUPADO[e] : '';
}
function noSalioCerrado(a) { var e = fotoDe(a).envio; return !e || L(a).noSalioCerrado === e.id; }
function ultimoEsMio(a) { var c = S.conv[a.id]; if (!c || !c.turnos || !c.turnos.length) return false; return c.turnos[c.turnos.length - 1].rol === 'yo'; }

/* ---------- uso del motor, según lo que el motor deja ver ---------- */
var LOCALES = { ollama: 1, lmstudio: 1, 'lm-studio': 1, local: 1 };
function usoDe(a) {
  var vivo = null, p = S.pant[a.id];
  if (p && p.uso && Object.keys(p.uso).length) vivo = p.uso;
  var snap = (S.usoSnap[a.id] || {}).uso || null, u = {};   // lo que su motor informó por su vía oficial (capa de control)
  [snap, vivo].forEach(function (o) { if (o) for (var k in o) if (o[k] != null && o[k] !== '') u[k] = o[k]; });
  var mc = motorChat(a), tipo;
  if (mc === 'claude-code') { tipo = 'sub'; delete u.gasto; }   // Claude Code es de plan: su «$» es lo que costaría por API, no lo que pagas
  else tipo = u.sesion != null || u.semana != null ? 'sub' : u.creditos ? 'cuota' : u.gasto ? 'api' : LOCALES[mc] ? 'local' : 'nada';
  return { tipo: tipo, u: u, vivo: !!vivo, edad: snap && !vivo && snap.viejo ? snap.edad : 0 };
}
function pctNum(v) { var n = parseFloat(v); return isNaN(n) ? null : Math.max(0, Math.min(100, n)); }

/* ---------- lo que la página recuerda de un arranque a otro ----------
   El tema, el agente activo, la pestaña que ves de cada agente, «enviar con ⌘↵», el motor por defecto y «Ahora no».
   Vive en Workspace (/api/front/inicio lo trae en «pagina»; /api/front/pagina lo anota), no en el navegador: la página
   se sirve en un puerto distinto en cada arranque y para el navegador cada puerto es otro sitio, con su localStorage
   vacío (todo se perdía cada vez). El localStorage queda como copia: con ella se pinta antes de que conteste Workspace
   y, lo que solo estaba ahí (lo de antes), se pasa a Workspace una vez. */
var PAG_LOCAL = { tema: 'ws.tema', tema_predeterminado: 'ws.cfg.temaPredeterminado', cmd_enter: 'ws.cfg.cmdEnter',
  motor_def: 'ws.cfg.motorDef', activo: 'ws.front.act', tabs: 'ws.front.tabs' };
var PAG_LUEGO = 'ws.conf.luego.';          /* «Ahora no»: una llave por agente */
var PAG = { d: {}, listo: false, pend: null, reloj: 0 };
function pagLocal(k) {
  try {
    if (k === 'luego') {
      var m = {}, n = 0;
      for (var i = 0; i < localStorage.length; i++) {
        var c = localStorage.key(i); if (!c || c.indexOf(PAG_LUEGO) !== 0) continue;
        var e = null; try { e = JSON.parse(localStorage.getItem(c)); } catch (_) {}
        if (typeof e === 'string' && e) { m[c.slice(PAG_LUEGO.length)] = e; n++; }
      }
      return n ? m : null;
    }
    var crudo = localStorage.getItem(PAG_LOCAL[k]);
    if (crudo === null || crudo === undefined) return null;
    return k === 'activo' ? crudo : JSON.parse(crudo);
  } catch (_) { return null; }
}
function pagLocalPon(k, v) {
  try {
    if (k === 'luego') { Object.keys(v || {}).forEach(function (id) { localStorage.setItem(PAG_LUEGO + id, JSON.stringify(v[id])); }); return; }
    if (v === null || v === undefined) localStorage.removeItem(PAG_LOCAL[k]);
    else localStorage.setItem(PAG_LOCAL[k], k === 'activo' ? v : JSON.stringify(v));
  } catch (_) {}
}
/* antes de que conteste Workspace, la copia del navegador; después, lo de Workspace */
function pagGet(k) { if (!PAG.listo && !(k in PAG.d)) return pagLocal(k); return k in PAG.d ? PAG.d[k] : null; }
function pagSet(k, v) {
  if (v === undefined) v = null;
  if (v === null) delete PAG.d[k]; else PAG.d[k] = v;
  pagLocalPon(k, v);
  PAG.pend = PAG.pend || {}; PAG.pend[k] = v;
  clearTimeout(PAG.reloj); PAG.reloj = setTimeout(pagMandar, 200);      /* varios cambios seguidos, un solo viaje */
}
function pagMandar() { var c = PAG.pend; PAG.pend = null; PAG.reloj = 0; if (c) post('/api/front/pagina', { cambios: c }).catch(function () {}); }
/* llega con /api/front/inicio; solo la primera vez (inicio se repite cada 30 s y no debe pisar lo que cambias aquí) */
function pagCargar(d) {
  if (PAG.listo || !d || typeof d !== 'object') return;
  var nuevo = {}, falta = null;
  Object.keys(d).forEach(function (k) { nuevo[k] = d[k]; pagLocalPon(k, d[k]); });
  Object.keys(PAG_LOCAL).concat(['luego']).forEach(function (k) {
    if (k in nuevo) return;
    var v = pagLocal(k); if (v === null) return;
    nuevo[k] = v; (falta = falta || {})[k] = v;                           /* lo de antes: se pasa a Workspace */
  });
  Object.keys(PAG.d).forEach(function (k) { nuevo[k] = PAG.d[k]; });
  PAG.d = nuevo; PAG.listo = true;
  if (falta) { Object.keys(PAG.pend || {}).forEach(function (k) { falta[k] = PAG.pend[k]; }); PAG.pend = falta; clearTimeout(PAG.reloj); PAG.reloj = setTimeout(pagMandar, 200); }
}

/* ---------- cargas ---------- */
function cargarInicio() {
  return api('/api/front/inicio').then(function (d) {
    var antes = {}; S.agentes.forEach(function (a) { antes[a.id] = a; });
    S.formas = d.formas || []; S.colores = d.colores || []; S.ajustes = d.ajustes || {};
    if (d.guia_vista) S.guiaVista = true;
    if (!PAG.listo && d.pagina) { pagCargar(d.pagina); if (typeof cfgAplicarTema === 'function') cfgAplicarTema(); }
    S.agentes = (d.agentes || []).map(function (x) {
      var a = antes[x.id] || { id: x.id };
      a.n = x.nombre; a.nOrig = x.nombre_original; a.lema = x.lema; a.motor = x.motor; a.status = x.status;
      a.f = x.forma; a.c = x.color; a.fijas = x.fijas || []; a.detenidas = x.detenidas || [];
      return a;
    });
    /* modo escritorio · «Seguir en la página»: el monito abre la página en su agente (#a=<agente>); se usa una vez */
    var pedido = agenteDelEnlace();
    if (pedido && ag(pedido)) { S.act = pedido; pagSet('activo', pedido); }
    if (!S.act || !ag(S.act)) { var guardado = pagGet('activo'); S.act = ag(guardado) ? guardado : (S.agentes[0] || {}).id || null; }
  });
}
function agenteDelEnlace() {
  var m = /^#a=([A-Za-z0-9._-]{1,64})$/.exec(location.hash || '');
  if (!m) return '';
  try { history.replaceState(null, '', location.pathname + location.search); } catch (_) {}
  return m[1];
}
function cargarPestanas() {
  return api('/api/v2/pestanas').then(function (d) { var por = {}; (d.pestanas || []).forEach(function (p) { (por[p.agente] = por[p.agente] || []).push(p); }); S.pestanas = por; });
}
/* sus ejecuciones llegan en su foto; esto es para no esperar a la siguiente (al arrancar una skill) */
function cargarEjecuciones(a) {
  return api('/api/ejecuciones?agente=' + encodeURIComponent(a.id)).then(function (d) {
    ponerEjecuciones(a, (d.ejecuciones || []).filter(function (e) { return e.pestana === NAV; }));
    if ('vigente' in d) { (S.vig = S.vig || {})[a.id] = d.vigente || ''; var f = S.vivo[a.id]; if (f) f.skill_vigente = d.vigente || null; }
  }, function () { S.ejec[a.id] = S.ejec[a.id] || []; });
}
function ponerEjecuciones(a, lista) { S.ejec[a.id] = lista; }
/* agente-interfaz: si el agente se personaliza (su color, su monito o su nombre: la herramienta personalizar), su foto
   lo trae y se ve en vivo (monitoDe rehace su monito al cambiar color o forma). → true si cambió algo */
function ponerPerfil(a, p) {
  if (!p) return false;
  var c = COLORES.indexOf(p.color) >= 0 ? p.color : a.c, f = FORMAS.indexOf(p.forma) >= 0 ? p.forma : a.f;
  var n = p.nombre || a.nOrig || a.n;
  if (c === a.c && f === a.f && n === a.n) return false;
  a.c = c; a.f = f; a.n = n; return true;
}
function cargarSkills() { return api('/api/skills').then(function (d) { S.skills = d.skills || []; }, function () {}); }
/* F7: recién abierta la página los motores salen «verificando» (su sesión se revisa de fondo): se vuelve a preguntar a
   los pocos segundos mientras alguno lo esté, no al minuto */
var MOTORES_OTRA = { n: 0, t: null };
function cargarMotores() {
  return api('/api/sistema/motores').then(function (d) {
    S.motores = d.motores || [];
    var falta = S.motores.some(function (m) { return m.estado === 'verificando'; });
    clearTimeout(MOTORES_OTRA.t);
    if (falta && MOTORES_OTRA.n++ < 20) MOTORES_OTRA.t = setTimeout(cargarMotores, 3000); else if (!falta) MOTORES_OTRA.n = 0;
    if (typeof pintarTop === 'function') pintarTop();
  }, function () {});
}
function cargarUsoSnap(a) { return api('/api/v2/uso?agente=' + encodeURIComponent(a.id)).then(function (d) { S.usoSnap[a.id] = d; }, function () {}); }
/* la conversación por versión: el servidor manda solo lo que cambió desde la que tenemos (`desde` = índice absoluto
   de su primer turno) y aquí se pega sobre lo que había; se queda la ventana de los últimos `n` */
function juntarConversacion(c, d, slug) {
  if (d.igual && c && c.slug === slug) return c;
  var cb = c && c.slug === slug ? (c.total || 0) - (c.turnos || []).length : 0;
  var t = c && c.slug === slug && d.desde >= cb ? c.turnos.slice(0, d.desde - cb).concat(d.turnos || []) : (d.turnos || []);
  d.turnos = d.n != null ? t.slice(Math.max(0, t.length - d.n)) : t;
  return d;
}
/* desde dónde buscar lo que mandas: los turnos ya guardados de su conversación. El turno en curso (`vivo`) solo se
   enseña y puede irse: F2 (E2E v4) lo que Hermes tenía escrito en su caja contaba, tu mensaje quedaba antes de su
   `base` y se veía dos veces (el bueno y su copia «pendiente») hasta el siguiente */
function baseDe(cv, slug) {
  if (!cv || cv.slug !== slug) return 0;
  var t = cv.turnos || [], u = t[t.length - 1];
  return Math.max(0, (cv.total || 0) - (u && u.vivo ? 1 : 0));
}
/* los turnos NUEVOS desde lo que mandaste ({slug, base}) y si tu texto ya está entre ellos */
function nuevosDesde(t, d, slug, x) { return t.slice(Math.max(0, t.length - Math.max(0, (d.total || t.length) - (x.slug === slug ? x.base : 0)))); }
function yaLlego(nuevos, texto) {
  var norm = function (z) { return (z || '').replace(/\s+/g, ' ').trim(); }, aguja = norm(texto).slice(0, 40);
  return nuevos.some(function (x) { return x.rol === 'yo' && norm(x.texto).indexOf(aguja) >= 0; });
}
function cargarConversacion(a) {
  var slug = slugChat(a);
  if (!slug) { S.conv[a.id] = { slug: null, turnos: [], total: 0 }; return Promise.resolve(false); }
  var c0 = S.conv[a.id], v = c0 && c0.slug === slug && c0.v ? '&v=' + encodeURIComponent(c0.v) : '', fv = fotoDe(a).conv;
  return api('/api/v2/conversacion?agente=' + encodeURIComponent(a.id) + '&slug=' + encodeURIComponent(slug) + v).then(function (r) {
    if (slugChat(a) !== slug) return false;     // H4-a: cambiaste de pestaña mientras llegaba: es de la otra
    var d = juntarConversacion(S.conv[a.id], r, slug), t = d.turnos || [], u = t[t.length - 1], ms = d.motores || [];
    d.fv = fv;
    var firma = slug + '|' + (d.total || 0) + '|' + t.length + '|' + (u ? (u.rol + (u.texto || '').length + (u.herr || []).length) : '') + '|' + ms.length + (ms.length ? ms[ms.length - 1].motor : '');
    var cambio = !S.conv[a.id] || S.conv[a.id].firma !== firma;
    d.slug = slug; d.firma = firma; S.conv[a.id] = d; (S.convs || (S.convs = {}))[a.id + '|' + slug] = d;
    /* lo que mandaste se ve hasta que aparece en SU conversación: solo se busca entre los turnos NUEVOS (antes se
       comparaba con todo y un mensaje parecido viejo lo borraba al instante: «desaparecía») */
    var p = L(a).pendiente;
    if (p) {
      var nuevos = nuevosDesde(t, d, slug, p), llego = yaLlego(nuevos, p.texto);
      var contesto = nuevos.some(function (x) { return x.rol !== 'yo' && !x.arranque; }) && nuevos.length >= 2;   // el arranque no contesta (F19)
      var vence = (L(a).enviando ? 30 : 10) * 60000;
      if (llego || contesto || Date.now() - p.ts > vence) { L(a).pendiente = null; cambio = true; }
    }
    /* el que no contestó en un minuto y al final salió (su motor abrió tarde): su tarjeta ya no va (F3d) */
    var ns = L(a).noSalio;
    if (ns && ns.tarde && ns.texto && yaLlego(nuevosDesde(t, d, slug, ns), ns.texto)) { L(a).noSalio = null; cambio = true; }
    return cambio;
  }, function () { return false; });
}

/* ---------- escuchar al servidor ----------
   Un long-poll a /api/v2/vivo: vuelve en cuanto algo cambia (o a los 25 s sin nada). Cada respuesta trae solo las
   fotos que cambiaron desde nuestra versión, así que reconectar no pierde nada. Si falla dos veces seguidas, se pasa
   al sondeo (la misma ruta sin esperar, cada 3 s) y al minuto se vuelve a intentar el long-poll. */
var VIVO = { v: 0, e: '', fallas: 0, modo: 'push', vuelve: 0, t: null, chat: null, gen: 0, espera: 0 };
/* quién escucha (la página tope los long-polls por cliente: cada pestaña del navegador es uno) y, con la pestaña
   escondida, sin long-poll: una pregunta cada VIVO_ESCONDIDA_MS; al volver a verla, enseguida */
var VIVO_C = 'p' + Math.random().toString(36).slice(2, 12), VIVO_ESCONDIDA_MS = 30000;
function escondida() { return typeof document !== 'undefined' && document.hidden === true; }
if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('visibilitychange', function () { if (!escondida() && VIVO.espera) { VIVO.espera = 0; escuchar(); } });
}
/* ¿terminó un cambio de motor? El de la página (pagina_v2.cambiar_motor) es inmediato: su foto nunca dice «cambiando»,
   trae `cambio` con paso «listo» (o «error») unos segundos. Terminó si llega uno nuevo, o si la foto sale de «cambiando» */
function cambioHecho(antes, f) {
  if (antes.estado === 'cambiando' && f.estado !== 'cambiando') return true;
  var s = f.cambio, s0 = antes.cambio;
  return !!(s && (s.paso === 'listo' || s.paso === 'error') && !(s0 && s0.t === s.t && s0.paso === s.paso));
}
function aplicarVivo(d) {
  /* lo de antes se guarda ANTES de vaciar: /api/v2/vivo manda siempre la foto completa, y comparar contra lo ya vaciado
     no veía ni el fin de un cambio de motor ni que cambiaron sus pendientes */
  var previo = S.vivo;
  if (d.completo) { S.vivo = {}; S.vivoCrudo = {}; }
  var a = activo(), antes = a ? JSON.stringify([(previo[a.id] || {}).conv, (S.ejec[a.id] || []).map(function (e) { return [e.id, e.estado, pasosHechos(e), (e.pasos || []).length]; })]) : '';
  var perfil = false;                   // el agente que ves se personalizó: su hilo también (sus monitos)
  Object.keys(d.agentes || {}).forEach(function (id) {
    var x = ag(id), antes = previo[id] || {}, f = ponerFoto(id, d.agentes[id]);
    if (x && cambioHecho(antes, f)) terminoCambio(x);
    if (antes.pend && antes.pend !== f.pend) { delete PEND_CACHE[id]; if (id === S.act && PEND_UPD) setTimeout(PEND_UPD, 0); }
    var pe = x && L(x).pendiente;     // no salió: queda su tarjeta con la salida, no la burbuja «enviando»
    if (pe && f.envio && f.envio.id === pe.cid && /^(no_se_mando|sin_eco|atorado|no_abrio|quitado)$/.test(f.envio.estado)) L(x).pendiente = null;
    if (x) { if (ponerPerfil(x, f.perfil) && id === S.act) perfil = true; ponerEjecuciones(x, f.ejecuciones || []); setTimeout(function () { revisarDetenerY(x); }, 0); }
    if (f.estado === 'termino') setTimeout(function () { pintarRiel(); pintarTop(); if (S.PANEL === 'agente' && AHORA_UPD) AHORA_UPD(); }, FESTEJO_MS + 100);
  });
  VIVO.v = d.v; VIVO.e = d.e;
  pintarRiel(); pintarTop(); if (typeof pintarTabs === 'function') pintarTabs(); pintarActiva(); pintarEstadoVivo(); pintarUsoCaja(); pintarCaja();
  if (perfil) pintarHilo();
  if (S.PANEL === 'agente' && AHORA_UPD) AHORA_UPD(); if (S.PANEL === 'skills') refrescarSkillsPanel();
  a = activo();
  if (a) {
    var f2 = S.vivo[a.id] || {}, despues = JSON.stringify([f2.conv, (S.ejec[a.id] || []).map(function (e) { return [e.id, e.estado, pasosHechos(e), (e.pasos || []).length]; })]);
    if (despues !== antes || !S.conv[a.id] || S.conv[a.id].fv !== f2.conv) sondeoChat();
  }
}
function detenerY(a, que, hacer, cerrar) {
  L(a).detenerY = { que: que, hacer: hacer, cerrar: cerrar, desde: Date.now() };
  parar(a, NAV); pintarEstadoVivo();
  setTimeout(function () { revisarDetenerY(a); }, 600);        // si no estaba ocupado de verdad, no hay que esperar
}
function revisarDetenerY(a) {
  var d = L(a).detenerY;
  if (!d) return;
  /* H14: detenido en una pregunta o un permiso de su terminal, «Detener» no lo saca (Cursor vuelve a pedir lo mismo) y el
     cambio normal rebota: la salida es «Cerrar y cambiar», ya, sin esperar */
  if (fotoDe(a).estado === 'esperandote') { if (!d.atorado) { d.tarde = d.atorado = true; pintarEstadoVivo(); } return; }
  if (!ocupadoDe(a)) { L(a).detenerY = null; d.hacer(); return; }
  if (Date.now() - d.desde > DETENER_ESPERA_MS && !d.tarde) { d.tarde = true; pintarEstadoVivo(); }
}
var DETENER_ESPERA_MS = 20000;
/* el cambio de motor terminó: ahora sí, su motor nuevo en el chip, el uso y el panel */
function terminoCambio(a) {
  L(a).cambio = null;
  cargarPestanas().then(function () { pintarTop(); });
  if (a.id !== S.act) return;
  cargarUsoSnap(a).then(function () { pintarUsoCaja(); if (S.PANEL === 'agente' && !S.EDIT) pintarPanel(); });
  setTimeout(function () { var ta = $('#ta'); if (!ta.disabled) ta.focus(); }, 0);
}
function escuchar() {
  clearTimeout(VIVO.t); VIVO.espera = 0;
  var gen = ++VIVO.gen, oculta = escondida(), espera = VIVO.modo === 'push' && !oculta ? 25 : 0, reintenta = 0;
  api('/api/v2/vivo?v=' + VIVO.v + '&e=' + encodeURIComponent(VIVO.e) + '&espera=' + espera + '&act=' + encodeURIComponent(S.act || '') + '&c=' + VIVO_C).then(function (d) {
    if (gen !== VIVO.gen) return;
    VIVO.fallas = 0; aplicarVivo(d);
  }, function (e) {
    if (gen !== VIVO.gen) return;
    if (e && e.ocupado) { reintenta = 1000 * Math.max(1, (e.datos && e.datos.reintenta) || 5); return; }   // muchos a la vez
    VIVO.fallas++; if (!e || e.status === undefined) marcarConectado(false);
    if (VIVO.fallas >= 2 && VIVO.modo === 'push') { VIVO.modo = 'sondeo'; VIVO.vuelve = Date.now() + 60000; }
    if (window.console) console.warn('vivo', e);
  }).then(function () {
    if (gen !== VIVO.gen) return;
    if (VIVO.modo === 'sondeo' && Date.now() > VIVO.vuelve) VIVO.modo = 'push';
    var pausa = reintenta || (VIVO.fallas ? Math.min(15000, 1000 * Math.pow(2, VIVO.fallas - 1)) : VIVO.modo === 'push' ? 0 : 3000);
    if (escondida()) { pausa = Math.max(pausa, VIVO_ESCONDIDA_MS); VIVO.espera = 1; }
    VIVO.t = setTimeout(escuchar, pausa);
  });
}
var sondeoGlobal = escuchar;
/* la conversación del agente que ves: cuando su foto dice que cambió (y una vez cada 30 s, por si acaso) */
var CHAT = { corre: false, otra: false, t: null };
function sondeoChat() {
  var a = activo(); if (!a) return;
  if (CHAT.corre) { CHAT.otra = true; return; }
  CHAT.corre = true; clearTimeout(CHAT.t);
  cargarConversacion(a).then(function (cambio) {
    if (cambio) pintarHilo(); else pintarEstadoVivo();
    pintarTop(); pintarUsoCaja();
  }).catch(function (e) { if (window.console) console.warn('chat', e); }).then(function () {
    CHAT.corre = false;
    if (CHAT.otra) { CHAT.otra = false; sondeoChat(); return; }
    CHAT.t = setTimeout(sondeoChat, 30000);
  });
}
/* después de algo que hiciste (mandar, elegir, teclas): la conversación, ya; el estado llega solo */
function acelerar() { setTimeout(sondeoChat, 250); }
