/* ================= la conversación (una sola por agente) ================= */
/* texto con lo mínimo de formato: bloques ``` , `código` y **negritas**; el resto, tal cual */
function texto(nodo, s) {
  (s || '').split('```').forEach(function (parte, i) {
    if (i % 2) { var pre = el('pre', null, parte.replace(/^[a-zA-Z0-9_-]*\n/, '')); nodo.appendChild(pre); return; }
    parte.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/).forEach(function (t) {
      if (!t) return;
      if (t.charAt(0) === '`' && t.length > 2) nodo.appendChild(el('code', null, t.slice(1, -1)));
      else if (t.slice(0, 2) === '**' && t.length > 4) nodo.appendChild(el('b', null, t.slice(2, -2)));
      else nodo.appendChild(document.createTextNode(t));
    });
  });
  return nodo;
}
var HERR_N = { Read: 'leyó', Edit: 'editó', Write: 'escribió', Bash: 'corrió un comando', Ran: 'corrió un comando', Shell: 'corrió un comando', Explored: 'exploró', Called: 'usó una herramienta', Grep: 'buscó', Glob: 'buscó archivos', Task: 'mandó a un ayudante', Agent: 'mandó a un ayudante', WebFetch: 'leyó una página', WebSearch: 'buscó en la web' };
/* «corrió un comando» ×5 → «corrió 5 comandos» (F17); tocarla abre cuáles */
var HERR_PL = { 'corrió un comando': 'corrió {n} comandos', 'leyó': 'leyó {n} archivos', 'editó': 'editó {n} archivos', 'escribió': 'escribió {n} archivos',
  'buscó': 'buscó {n} veces', 'buscó archivos': 'buscó archivos {n} veces', 'mandó a un ayudante': 'mandó a {n} ayudantes', 'leyó una página': 'leyó {n} páginas',
  'buscó en la web': 'buscó en la web {n} veces', 'exploró': 'exploró {n} veces', 'usó una herramienta': 'usó {n} herramientas' };
function resumenHerr(h) {
  var orden = [], cuenta = {};
  h.forEach(function (x) { var t = HERR_N[x.n] || x.n; if (!cuenta[t]) { cuenta[t] = 0; orden.push(t); } cuenta[t]++; });
  var partes = orden.map(function (t) { return cuenta[t] > 1 ? (HERR_PL[t] || t + ' ×{n}').replace('{n}', cuenta[t]) : t; });
  return partes.slice(0, 3).join(' · ') + (partes.length > 3 ? ' y ' + (partes.length - 3) + ' más' : '');
}
function lineaHerr(h) {
  var w = el('div', 'herr abre'), lista = null;
  w.appendChild(el('span', null, resumenHerr(h)));
  w.title = 'Ver cuáles';
  w.onclick = function (e) {
    e.stopPropagation();
    if (lista) { lista.remove(); lista = null; return; }
    lista = el('div', 'herr-lista', h.map(function (x) { return (HERR_N[x.n] || x.n) + (x.d ? ' · ' + x.d : ''); }).join('\n')); w.appendChild(lista);
  };
  return w;
}
/* la instrucción de una skill (localhost_web._instruccion): `workspace pasos s-…` desde N2, la herramienta
   reportar_avance en los motores que preguntan, y pasos.py en las de antes */
function esInstruccionSkill(t) { return t.rol === 'yo' && /pasos\.py|\bworkspace(?:\.cmd)?\s+pasos\s+s-|\breportar_avance\b/.test(t.texto || ''); }
function skillDeInstruccion(a, t) {
  var e = (S.ejec[a.id] || []).filter(function (x) { return (t.texto || '').indexOf(x.id) >= 0; })[0];
  return e ? e.skill : '';
}
function cerca(f) { return f.scrollHeight - f.scrollTop - f.clientHeight < 120; }
function cartasDe(a) {
  var vig = ejecVigente(a), hecho = L(a).detenidas || {};
  return (S.ejec[a.id] || []).filter(function (e) {
    if (vig && e.id === vig.id) return true;
    if (hecho[e.id] || detenida(a, e)) return false;
    var t = Date.parse(e.actualizado || e.creado || '') || 0;
    return t && Date.now() - t < 24 * 3600 * 1000;
  }).reverse();
}
function pintarHilo() {
  var a = activo(), C = $('#col'), f = $('#feed'), pegado = cerca(f);
  if (!a) {                                         /* AG8-b: el vacío trae su botón (la misma ventana de «+») */
    C.textContent = ''; C._mapa = null;
    var v0 = el('div', 'vacio'); v0.appendChild(el('b', null, 'No hay agentes en esta computadora todavía.'));
    var nb = el('button', 'bt p', '+ Agregar agente'); nb.onclick = function () { crearAgente(); }; v0.appendChild(nb);
    var cb = el('button', 'bt', 'Ya tengo un agente ›'); cb.onclick = function () { crearAgente('cargar'); }; v0.appendChild(cb);
    C.appendChild(v0); return;
  }
  var c = S.conv[a.id], slug = slugChat(a), piezas = [];
  pintarCaja();
  if (!slug && !L(a).pendiente && !L(a).skillPend) {
    piezas.push({ k: 'vacio', f: firma(a.n + a.lema + a.c + a.f), quieto: true, hacer: function () {
      var v = el('div', 'vacio'); v.appendChild(monitoDe('vacio', a, 84)); v.appendChild(el('b', null, a.n));
      v.appendChild(el('span', null, a.lema || 'Escríbele para empezar. Toda su conversación vive aquí.')); return v;
    } });
    var cs = cartasDe(a);
    porHora(cs.map(function (e) { return { t: horaSkill(e), p: piezaTarjeta(a, e) }; })
      .concat(finesDe(cs).map(function (x) { return { t: x.t, p: piezaFin(a, x.e) }; }))).forEach(function (x) { piezas.push(x.p); });
  } else {
    /* las skills: su marca donde empezó y, si terminó, su tarjeta donde terminó (antes del primer turno de después) */
    var turnos = (c && c.turnos) || [], cartas = cartasDe(a), puestas = {}, fines = finesDe(cartas), nf = 0;
    var base = Math.max(0, ((c && c.total) || turnos.length) - turnos.length);   // índice absoluto: la ventana de 160 turnos se corre
    /* un segmento por motor: donde empieza otro, «Siguió con X»; lo que el motor contesta a su arranque es un chip */
    var segs = (c && c.motores) || [], motor = motorChat(a), sig = 0;
    segs.forEach(function (s, n) { if (s.i <= base) { motor = s.motor; sig = n + 1; } });   // lo de antes de la ventana
    var grupo = null;                     // turnos seguidos que solo corrieron herramientas: una sola línea (F17)
    function cerrarGrupo() { if (grupo) { var g = grupo; grupo = null; piezas.push({ k: g.k, f: firma(JSON.stringify(g.herr)), hacer: function () { var w = el('div', 'grupo'); w.appendChild(lineaHerr(g.herr)); return w; } }); } }
    /* B43 (modo chat): «Terminó» va DESPUÉS del mensaje final de su turno: antes de tu siguiente mensaje (o de la marca de
       otra skill), nunca entre lo que contesta. Antes salía arriba de su respuesta («no reportó que terminaste») */
    function ponerFines(hasta) { while (hasta && nf < fines.length && fines[nf].t <= hasta && puestas[fines[nf].e.id]) { cerrarGrupo(); piezas.push(piezaFin(a, fines[nf++].e)); } }
    var ultimoYo = 0;
    function cortes(hasta) {
      while (sig < segs.length && segs[sig].i <= hasta) {
        cerrarGrupo();
        var s = segs[sig++]; motor = s.motor;
        piezas.push({ k: 'siguio' + sig, f: s.motor, quieto: true, hacer: (function (m) { return function () { return el('div', 'when', 'Siguió con ' + motorN(m)); }; })(s.motor) });
      }
    }
    /* H3 (rama de prueba marca-lab): lo que terminó una sesión oficial llega como una línea, antes del turno que le
       sigue (pagina_sesiones: c.sesiones, con el índice absoluto de ese turno). No es un turno: el hub la pinta igual */
    var lsx = ((c && c.sesiones) || []).filter(function (x) { return x.i >= base; }), ls = 0;
    function deSesiones(hasta) {
      while (ls < lsx.length && lsx[ls].i <= hasta) {
        cerrarGrupo();
        var x = lsx[ls++];
        piezas.push({ k: 'ses' + x.ts + '|' + (x.nombre || ''), f: firma(JSON.stringify(x)), quieto: true, hacer: (function (x) { return function () {
          return el('div', 'when ses', 'Terminó en ' + motorN(x.motor) + (x.nombre ? ' · «' + x.nombre + '»' : '') + (x.texto ? ': ' + x.texto : ''));
        }; })(x) });
      }
    }
    turnos.forEach(function (t, i) {
      var ts = Date.parse(t.ts || '') || 0, abs = base + i;
      deSesiones(abs);
      cortes(abs);
      cartas.forEach(function (e) { var ce = horaSkill(e); if (!puestas[e.id] && ts && ce && ce <= ts && !esInstruccionSkill(t)) { ponerFines(ce); cerrarGrupo(); piezas.push(piezaTarjeta(a, e)); puestas[e.id] = 1; } });
      if (t.rol === 'yo') { ponerFines(ts); ultimoYo = ts || ultimoYo; }
      if (t.arranque) { cerrarGrupo(); if (!i || !turnos[i - 1].arranque) piezas.push(piezaListo(motor, 't' + abs)); return; }
      if (t.rol !== 'yo' && !(t.texto || '').trim() && (t.herr || []).length) {
        if (!grupo) grupo = { k: 'hg' + abs, herr: [] };
        grupo.herr = grupo.herr.concat(t.herr); return;
      }
      cerrarGrupo();
      piezas.push(piezaTurno(a, t, 't' + abs));
    });
    cerrarGrupo();
    deSesiones(Infinity);                                                                   // lo que terminó después del último turno
    cortes(Infinity);                                                                       // el motor nuevo, aún sin turnos
    /* B43: con su turno en curso, el «Terminó» de ese turno va abajo de lo que escribe en vivo (en la cola), no arriba */
    var pv = S.pant[a.id], resto = fines.slice(nf), vivos = pv && pv.trabajando ? resto.filter(function (x) { return x.t > ultimoYo; }) : [];
    L(a).finesVivos = vivos.map(function (x) { return x.e; });
    porHora(cartas.filter(function (e) { return !puestas[e.id]; }).map(function (e) { return { t: horaSkill(e), p: piezaTarjeta(a, e) }; })
      .concat(resto.filter(function (x) { return vivos.indexOf(x) < 0; }).map(function (x) { return { t: x.t, p: piezaFin(a, x.e) }; }))).forEach(function (x) { piezas.push(x.p); });
    if (c && c.soporta === false && !turnos.length && slug) piezas.push({ k: 'sin-soporte', f: '1', hacer: function () { return el('div', 'aviso', 'Su conversación aparece aquí cuando su motor la tenga abierta.'); } });
  }
  var w = C._cola || (C._cola = (function () { var x = el('div', 'cola'); x.id = 'cola'; return x; })());
  piezas.push({ k: 'cola', f: 'cola', quieto: true, hacer: function () { return w; } });
  reconciliar(C, piezas, a.id + '|' + slug + '|' + (c ? 'c' : 'x'));   // cuando llega la conversación por primera vez, no se anima entera
  llenarCola(w, a);
  if (pegado) setTimeout(function () { f.scrollTop = f.scrollHeight; }, 0);
}
function piezaTurno(a, t, k) {
  return { k: k, f: firma(t.rol + '|' + (t.texto || '') + '|' + (t.herr || []).length + '|' + !!t.contexto + '|' + !!t.cortado + '|' + (esInstruccionSkill(t) ? skillDeInstruccion(a, t) : '') + '|' + JSON.stringify(t.archivos || [])), hacer: function () { return burbuja(a, t); } };
}
function piezaListo(m, k) {
  return { k: k, f: 'listo' + m, quieto: true, hacer: function () { var c = el('div', 'listo-c'); c.appendChild(el('i')); c.appendChild(el('span', null, 'Listo con ' + motorN(m))); return c; } };
}
/* skills v11, en el hilo: la marca «Empezó» donde empezó (su proceso vive a la derecha o sobre la caja) y, al terminar,
   la tarjeta «Terminó» en su hora de fin. La hora de fin es su última escritura (pasos.guardar): después del «fin» nadie
   la vuelve a guardar. Sin hora, al final. */
function horaSkill(e, fin) { return Date.parse((fin && e.actualizado) || e.creado || '') || 0; }
function finesDe(cartas) {
  return porHora(cartas.filter(function (e) { return e.estado === 'listo'; }).map(function (e) { return { t: horaSkill(e, true) || 8.64e15, e: e }; }));
}
function porHora(xs) { return xs.sort(function (x, y) { return x.t - y.t; }); }      // estable: a la misma hora, su orden
function piezaTarjeta(a, e) {
  var vig = ejecVigente(a), viva = !!(vig && vig.id === e.id);
  /* la firma, solo lo que se ve: al terminar la marca no se rehace (no repite su entrada) */
  return { k: 'sk|' + e.id, f: firma(JSON.stringify([modoMarca(e, viva), e.skill, a.c, a.f])), hacer: function () {
    /* una pieza que falla no rompe el hilo entero: queda su nombre en una línea */
    try { return marcaSkill(a, e, viva); } catch (err) { return el('div', 'marca3', 'Skill «' + nombreSkill(e.skill) + '»'); }
  } };
}
function piezaFin(a, e) {
  return { k: 'skfin|' + e.id, f: firma(JSON.stringify([e.skill, e.resumen, (e.pasos || []).length, archivoFin(e), a.c, a.f])), hacer: function () {
    try { return finSkill(a, e); } catch (err) { return el('div', 'marca3', 'Terminó «' + nombreSkill(e.skill) + '»'); }
  } };
}
/* ---------- presentación solo del navegador ----------
   Lo que el agente escribe para la terminal (el bloque 🧠 del final, el menú de archivo «📄 ruta / 1 — abrir…»)
   aquí se enseña como piezas propias. El agente no cambia nada: la regla vive en la página, para todos. */
var RE_CEREBRITO = /^\s*🧠\s*(Skill creada|Skill mejorada|check\s*✓)\s*:?\s*(.*)$/;
/* modo chat: otro cierre del cerebro que empieza con 🧠 (el de otro agente, otro formato): una línea discreta */
var RE_CEREBRITO_OTRO = /^\s*🧠\s*(\S.*)$/;
var RE_ARCHIVO = /^\s*📄\s*(\S.*?)\s*$/;
var RE_MENU = /1\s*[—–-]\s*abrir/i;
function presentar(txt) {
  var lineas = (txt || '').split('\n'), cuerpo = [], extras = [], dentroCodigo = false;
  for (var i = 0; i < lineas.length; i++) {
    var l = lineas[i];
    if (/^\s*```/.test(l)) {
      /* el menú de archivo suele venir dentro de un bloque de código: si lo es, se saca entero */
      var j = i + 1, bloque = [];
      while (j < lineas.length && !/^\s*```/.test(lineas[j])) bloque.push(lineas[j++]);
      var arch = bloque.map(function (x) { var m = x.match(RE_ARCHIVO); return m && m[1]; }).filter(Boolean);
      if (arch.length && RE_MENU.test(bloque.join('\n'))) { arch.forEach(function (r) { extras.push({ tipo: 'archivo', ruta: r }); }); i = j; continue; }
      dentroCodigo = !dentroCodigo; cuerpo.push(l); continue;
    }
    var mc = !dentroCodigo && l.match(RE_CEREBRITO);
    if (mc) { if (!/check/i.test(mc[1])) extras.push({ tipo: mc[1].toLowerCase().indexOf('creada') >= 0 ? 'skill-nueva' : 'skill-mejor', texto: mc[2] }); continue; }
    var mo = !dentroCodigo && l.match(RE_CEREBRITO_OTRO);
    if (mo) { extras.push({ tipo: 'cerebrito', texto: mo[1] }); continue; }
    var ma = !dentroCodigo && l.match(RE_ARCHIVO);
    if (ma && RE_MENU.test((lineas[i + 1] || '') + (lineas[i + 2] || ''))) { extras.push({ tipo: 'archivo', ruta: ma[1] }); i += RE_MENU.test(lineas[i + 1] || '') ? 1 : 2; continue; }
    cuerpo.push(l);
  }
  return { cuerpo: cuerpo.join('\n').replace(/\n{3,}/g, '\n\n').trim(), extras: extras };
}
function tarjetaExtra(a, x) {
  if (x.tipo === 'cerebrito') return el('div', 'herr', x.texto);
  if (x.tipo === 'archivo') {
    /* modo chat: también la de mostrar_archivo y la de un enlace a un archivo del cerebro (ruta relativa a él, y su título) */
    var ruta = x.ruta.replace(/^`|`$/g, ''), nombre = ruta.split(/[\\/]/).pop(), carpeta = ruta.slice(0, ruta.length - nombre.length).replace(/[\\/]$/, '');
    var donde = carpeta.split(/[\\/]/).slice(-2).join('/');
    var w = el('div', 'arch-c'); w.appendChild(el('i', 'di'));
    var tx = el('div', 'tx'); tx.appendChild(el('b', null, x.titulo || nombre)); tx.appendChild(el('small', null, x.titulo ? nombre + (donde ? ' · ' + donde : '') : donde)); tx.title = ruta; w.appendChild(tx);
    var b1 = el('button', 'chip p', 'Abrir'), b2 = el('button', 'chip', 'Mostrar en la carpeta');
    b1.onclick = function () { abrirLocal(a, ruta, 'abrir'); }; b2.onclick = function () { abrirLocal(a, ruta, 'revelar'); };
    w.appendChild(b1); w.appendChild(b2); return w;
  }
  var c = el('div', 'logro'), ic = el('span', 'li'); ic.appendChild(icono('skill')); c.appendChild(ic);
  var m = (x.texto || '').match(/`([^`]+)`/), nom = m ? m[1] : '', resto = (x.texto || '').replace(/`[^`]+`/, '').replace(/^[\s→—-]+/, '');
  var v = resto.match(/\(v?([\d.]+)\s*→\s*v?([\d.]+)\)/), qu = resto.replace(/\(v?[\d.]+\s*→\s*v?[\d.]+\)/, '').replace(/^[\s—-]+/, '').replace(/^`?skills\/[^`\s]*`?\s*/, '').trim();
  var t = el('div', 'tx'); t.appendChild(el('b', null, x.tipo === 'skill-nueva' ? 'Aprendió una skill nueva' : 'Mejoró una de sus skills'));
  t.appendChild(el('small', null, (nom || 'skill') + (v ? ' · v' + v[1] + ' → v' + v[2] : '') + (qu ? ' · ' + qu : '')));
  c.appendChild(t);
  if (nom) { var ver = el('button', 'chip', 'Ver'); ver.onclick = function () { S.SKQ = nom; abrirPanel('skills'); }; c.appendChild(ver); }
  return c;
}
function abrirLocal(a, ruta, modo) {
  post('/api/front/abrir', { agente: a.id, ruta: ruta, modo: modo }).then(function () {}, function (e) { nota(e.message, true); });
}
/* skills v11: lo que preguntó una skill, en el chat: una línea centrada y ligera (sin botones) y tu respuesta como tu
   burbuja con «Tu respuesta». La respuesta viaja como «Respuesta a «…»: …» (pagina_v2.responder) */
var RE_RESP = /^Respuesta a «([\s\S]*?)»: ([\s\S]*)$/;
function lineaPregunta(a, q, id) {
  var w = el('div', 'pc10 linea'), m = el('span', 'mslot'); m.appendChild(monitoDe('preg-' + id, a, 20)); w.appendChild(m);
  w.appendChild(el('span', null, a.n + ' te preguntó:')); w.appendChild(el('b', null, q));
  return w;
}
function respuestaPregunta(a, q, t, id, local) {
  var g = el('div', 'grupo-resp'), b = el('div', 'm yo resp11' + (local ? ' local' : ''));
  b.appendChild(el('small', null, 'Tu respuesta')); b.appendChild(el('span', null, t));
  g.appendChild(lineaPregunta(a, q, id)); g.appendChild(b);
  return g;
}
function respuestaEnHistorial(a, r) {
  var c = S.conv[a.id], ts = (c && c.turnos) || [];
  var id = 'rq-' + r.id.slice(-12);
  return ts.some(function (t) { return t.rol === 'yo' && t.envio_id === id; });
}
function burbuja(a, t) {
  var mr = t.rol === 'yo' && RE_RESP.exec(t.texto || '');
  if (mr) return respuestaPregunta(a, mr[1], mr[2].trim(), 'h' + firma(t.texto), false);
  if (esInstruccionSkill(t)) { var s = skillDeInstruccion(a, t), v = el('div', 'aviso'); v.appendChild(svg('skill')); var tt = el('span'); tt.appendChild(document.createTextNode('Activaste la skill ')); tt.appendChild(el('b', null, s || '')); v.appendChild(tt); return v; }
  var pr = t.rol === 'yo' ? { cuerpo: t.texto || '', extras: [] } : presentar(t.texto);
  /* modo chat: los archivos que enseñó (mostrar_archivo, o un enlace a un archivo de su cerebro), como tarjetas después
     de su texto. El servidor ya dejó su texto limpio (pagina_v2 · modo_chat.limpiar) */
  if (t.rol !== 'yo') (t.archivos || []).forEach(function (x) { if (x && x.ruta) pr.extras.push({ tipo: 'archivo', ruta: x.ruta, titulo: x.titulo || '' }); });
  var b = pr.cuerpo ? texto(el('div', 'm ' + (t.rol === 'yo' ? 'yo' : 'ag')), pr.cuerpo) : null;
  /* la nota de contexto que se le antepuso a tu mensaje (lo que habló con otros motores) no se enseña: se dice */
  if (t.contexto && b) { var gc = el('div', 'grupo yo'); gc.appendChild(b); gc.appendChild(el('div', 'herr', 'Le conté lo que hablaste con los otros motores')); return gc; }
  var herr = t.herr && t.herr.length && t.rol !== 'yo';
  /* B11: la página se cerró a media respuesta (su servidor murió): lo que alcanzó a decir, y que se cortó ahí */
  if (t.cortado && t.rol !== 'yo') {
    var gk = el('div', 'grupo'); if (herr) gk.appendChild(lineaHerr(t.herr)); if (b) gk.appendChild(b);
    gk.appendChild(el('div', 'herr', 'Se cortó aquí: Workspace se cerró antes de que terminara. Puedes pedírselo otra vez.'));
    return gk;
  }
  /* los permisos que contestaste en ese turno: su tarjeta, con lo que dijiste. Sin texto, nada más */
  if (t.rol !== 'yo' && t.permisos && t.permisos.length) {
    var gp = el('div', 'grupo');
    t.permisos.forEach(function (p) { gp.appendChild(tarjetaPermisoResuelto(p)); });
    if (b) { if (herr) gp.appendChild(lineaHerr(t.herr)); gp.appendChild(b); }
    if (b || (t.archivos || []).length) pr.extras.forEach(function (x) { gp.appendChild(tarjetaExtra(a, x)); });
    return gp;
  }
  if (!herr && !pr.extras.length) return b || el('div', 'nada');          /* nunca una burbuja vacía */
  var w = el('div', 'grupo');
  if (herr) w.appendChild(lineaHerr(t.herr));
  if (b) w.appendChild(b);
  pr.extras.forEach(function (x) { w.appendChild(tarjetaExtra(a, x)); });
  return w;
}
/* lo que va al final: lo recién enviado, la skill por arrancar, lo que pregunta su terminal y si está pensando.
   También por claves: lo que no cambió no se vuelve a dibujar. */
function pintarEstadoVivo() { var a = activo(), w = $('#cola'); if (!a || !w) return; var f = $('#feed'), pegado = cerca(f); llenarCola(w, a); if (pegado) f.scrollTop = f.scrollHeight; }
/* el permiso que pide su motor, como tarjeta en el chat: la respuesta va por la capa de control
   (responder_permiso). Si lo pidió su terminal (lo dicen sus hooks), se contesta ahí: «Ir a la terminal». */
var PERMISO_T = { permitir: 'Permitir', permitir_siempre: 'Siempre', negar: 'No' };
var PERMISO_HECHO = { permitir: 'Permitido', permitir_siempre: 'Permitido siempre', negar: 'Negado' };
/* el permiso en palabras simples, para quien no sabe de terminal: qué quiere hacer, sin el JSON de su herramienta (que
   va en «Ver detalle», cerrado). Cada motor lo manda distinto: Claude Code el nombre de su herramienta (Bash, Write,
   Edit, Read…) y su entrada; ACP un título («Escribir x.txt», «Run …») o su clase (edit, read, execute); Codex
   «comando» o «cambio de archivos»; OpenCode su acción (edit, shell) y los archivos. [ahora, ya contestado] */
/* B01 (cacería 19-nov): DÓNDE no se adivina. «de su carpeta» solo si la capa de control lo sabe (`que.fuera` false);
   FUERA de ella, con la ruta entera; sin saberlo, no se dice */
var PERM_QUE = {
  comando: ['Quiere correr un comando', 'Quiso correr un comando'],
  crear: ['Quiere crear un archivo', 'Quiso crear un archivo'],
  cambiar: ['Quiere cambiar un archivo', 'Quiso cambiar un archivo'],
  borrar: ['Quiere borrar un archivo', 'Quiso borrar un archivo'],
  imagen: ['Quiere leer una imagen', 'Quiso leer una imagen'],
  leer: ['Quiere leer un archivo', 'Quiso leer un archivo'],
  buscar: ['Quiere buscar en sus archivos', 'Quiso buscar en sus archivos'],
  web: ['Quiere abrir una página de internet', 'Quiso abrir una página de internet'],
  otra: ['Quiere usar una de sus herramientas', 'Quiso usar una de sus herramientas']
};
var PERM_DONDE = { dentro: { crear: ' en su carpeta', otro: ' de su carpeta' }, fuera: ' FUERA de su carpeta' };
/* sin `que` (un evento de antes): por el nombre EXACTO de su herramienta (Bash, Write, Edit…), nunca por palabras
   sueltas de un título o de una ruta («mkdir -p /tmp/caza-ver-dir» salía «leer» por «ver») */
var PERM_NOMBRE = [['borrar', /^(delete|remove|rm)$/], ['comando', /^(bash|shell|run|run command|run shell command|execute|exec|terminal|comando|command)$/],
  ['web', /^(webfetch|websearch|fetch|browse)$/], ['crear', /^(write|create)$/],
  ['cambiar', /^(edit|multiedit|notebookedit|patch|apply patch|str replace|cambio de archivos)$/], ['buscar', /^(grep|glob|search|find)$/],
  ['leer', /^(read)$/]];
var PERM_IMAGEN = /\.(png|jpe?g|gif|webp|svg|heic|bmp|tiff?)$/i;
function permisoDatos(pm) { try { return JSON.parse(pm.detalle); } catch (e) { return null; } }
function permisoClase(pm, d) {
  var n = String(pm.herramienta || '').toLowerCase().replace(/[_-]+/g, ' ').trim(), k = '';
  if (n.indexOf('mcp ') !== 0) PERM_NOMBRE.some(function (x) { if (x[1].test(n)) { k = x[0]; return true; } return false; });
  if (!k && d && typeof d === 'object' && !Array.isArray(d)) {
    k = (d.command || d.cmd) ? 'comando' : d.url ? 'web' : (d.old_string || d.new_string || d.edits || d.diff) ? 'cambiar'
      : (d.content !== undefined && (d.file_path || d.filePath || d.path)) ? 'crear' : (d.pattern || d.query) ? 'buscar' : '';
  }   /* una ruta sola no dice qué hace con ella (B01: un script de Python salía «leer») */
  /* su entrada llega recortada (a 400) y deja de ser JSON: sus claves se miran igual */
  var s = d === null ? String(pm.detalle || '') : '';
  if (!k && s) {
    var tiene = function (r) { return new RegExp('"(' + r + ')"\\s*:').test(s); };
    k = tiene('command|cmd') ? 'comando' : tiene('url') ? 'web' : tiene('old_string|new_string|edits|diff') ? 'cambiar'
      : tiene('content') && tiene('file_path|filePath|path') ? 'crear' : tiene('pattern|query') ? 'buscar' : '';
  }
  return k || 'otra';
}
/* el archivo que toca: el que manda la capa de control aparte (`archivo`, sacado antes de recortar su entrada) o, si
   no viene, el de su entrada */
function permisoArchivo(d, crudo, archivo) {
  var p = archivo || (d && (Array.isArray(d) ? d[0] : (d.file_path || d.filePath || d.path || d.file)));
  if (!p && d === null && crudo) { var m = String(crudo).match(/"(?:file_path|filePath|path|file)"\s*:\s*"([^"]+)"/); p = m && m[1]; }
  if (typeof p !== 'string' || !p) return '';
  return p.replace(/[\\\/]+$/, '').split(/[\\\/]/).pop().slice(0, 80);
}
/* → «Quiere crear un archivo en su carpeta: «notas.md».» · «Quiere cambiar un archivo FUERA de su carpeta: «/tmp/x».»
   · «Quiere correr un comando: «mkdir -p /tmp/x».» (`ya`: contestado). Con `que` (la capa de control: B01), lo que
   de verdad pide; sin él, lo de antes, sin decir dónde */
function permisoEnSimple(pm, ya) {
  var q = pm.que && PERM_QUE[pm.que.clase] ? pm.que : null;
  if (q) {
    var k2 = q.clase === 'leer' && PERM_IMAGEN.test(q.ruta || '') ? 'imagen' : q.clase, s = PERM_QUE[k2][ya ? 1 : 0];
    if (k2 === 'comando') return s + (q.comando ? ': «' + q.comando + '»' : '') + '.';
    if (q.ruta && k2 !== 'web') s += (q.fuera === true ? PERM_DONDE.fuera : q.fuera === false ? (k2 === 'crear' ? PERM_DONDE.dentro.crear : PERM_DONDE.dentro.otro) : '') + ': «' + q.ruta + '»';
    return s + '.';
  }
  var d = permisoDatos(pm), k = permisoClase(pm, d), f = permisoArchivo(d, pm.detalle, pm.archivo);
  if (k === 'leer' && PERM_IMAGEN.test(f)) k = 'imagen';
  return PERM_QUE[k][ya ? 1 : 0] + (f && k !== 'comando' && k !== 'web' && k !== 'otra' ? ': «' + f + '»' : '') + '.';
}
/* lo técnico (su herramienta y lo que le pasa), cerrado: para quien quiera mirarlo */
function detallePermiso(pm) {
  if (!pm.herramienta && !pm.detalle) return null;
  var d = permisoDatos(pm), x = d !== null && typeof d === 'object' ? JSON.stringify(d, null, 2) : (pm.detalle || '');
  var v = el('details', 'vd'); v.appendChild(el('summary', null, 'Ver detalle'));
  v.appendChild(el('pre', null, (pm.herramienta ? pm.herramienta + (x ? '\n' : '') : '') + x)); return v;
}
/* un permiso que ya contestaste: la misma tarjeta, con lo que dijiste en lugar de los botones */
function tarjetaPermisoResuelto(pm) {
  var q = el('div', 'm ag preg perm hecho'); q.appendChild(el('small', null, 'Pidió permiso'));
  texto(q, permisoEnSimple(pm, true));
  var vd = detallePermiso(pm); if (vd) q.appendChild(vd);
  q.appendChild(el('div', 'decide ' + (pm.decision === 'negar' ? 'no' : 'si'), PERMISO_HECHO[pm.decision] || pm.decision));
  return q;
}
function tarjetaPermiso(a, pm) {
  var q = el('div', 'm ag preg perm'); q.appendChild(el('small', null, pm.en_terminal ? 'Te pide permiso en su terminal' : 'Te pide permiso'));
  texto(q, permisoEnSimple(pm));
  var vd = detallePermiso(pm); if (vd) q.appendChild(vd);
  if (pm.en_terminal || !(pm.opciones || []).length) return pz(q, chipsFila([{ t: 'Ir a la terminal', p: true, run: function (b) { irTerminal(a, b); } }]));
  return pz(q, chipsFila(pm.opciones.map(function (d) {
    return { t: PERMISO_T[d] || d, p: d === 'permitir', run: function (b) {
      b.disabled = true;
      post('/api/v2/permiso', { agente: a.id, id: pm.id, decision: d }).then(function () { acelerar(); }, function (e) { nota(e.message, true); b.disabled = false; });
    } };
  })));
}
/* lo que una skill te pregunta: con opciones, un botón por opción; de texto, se contesta en la caja de abajo (es tu
   siguiente mensaje). Si su motor abrió un formulario en su terminal, se contesta ahí. La respuesta va por la capa
   de control, al mismo motor. */
function tarjetaPreguntaSkill(a, q) {
  var c = el('div', 'm ag preg'); c.appendChild(el('small', null, q.en_terminal ? 'Te pregunta en su terminal' : 'Te pregunta'));
  texto(c, q.pregunta);
  if (q.en_terminal) return pz(c, chipsFila([{ t: 'Ir a la terminal', p: true, run: function (b) { irTerminal(a, b); } }]));
  var ops = q.tipo === 'confirmar' ? ['Sí', 'No'] : (q.opciones || []);
  if (!ops.length) { c.appendChild(el('div', 'det', 'Contéstale en la caja de abajo.')); return c; }
  return pz(c, chipsFila(ops.map(function (o, i) {
    return { t: o, p: i === 0, run: function (b) {
      b.disabled = true;
      post('/api/v2/responder', { agente: a.id, id: q.id, texto: o }).then(function () { acelerar(); }, function (e) { nota(e.message, true); b.disabled = false; });
    } };
  })));
}
/* «Hacer ahora»: la revisión de skills que quedó pendiente le llega por la capa de control, sin teclear */
function piezaRevision(a, r) {
  return pz(el('div', 'aviso', 'Tiene ' + (r.n > 1 ? r.n + ' revisiones' : 'una revisión') + ' de skills pendiente.'),
    chipsFila([{ t: 'Hacer ahora', p: true, run: function (b) {
      b.disabled = true;
      post('/api/v2/revision', { agente: a.id }).then(function () { nota('Le mandé la revisión de skills'); acelerar(); }, function (e) { nota(e.message, true); b.disabled = false; });
    } }]));
}
/* «Ir a la terminal»: su panel en herdr. Abierto: se enfoca (su espacio y su pestaña) y se dice dónde está; si no se
   pudo enfocar, también, para que la encuentres. Cerrado: se abre con su lanzador de siempre. Nada se teclea, y nunca
   queda en silencio. `alDecir(texto)`: quien lo pidió puede dejar ese texto a la vista. */
var NOTA_TERMINAL_MS = 8000;
function dondeTerminal(d) {
  d = d || {};
  if (d.ventana) return 'ventana de la terminal';     // Windows: una ventana propia (su título lo pone el motor), no el hub
  var s = d.pestana ? 'pestaña «' + d.pestana + '»' : (d.panel ? 'panel ' + d.panel : '');
  if (d.espacio) s += (s ? ' del ' : '') + 'espacio «' + d.espacio + '»';
  if (d.sesion) s += (s ? ', ' : '') + 'sesión de herdr «' + d.sesion + '»';
  return s;
}
function irTerminal(a, b, alDecir) {
  if (b) b.disabled = true;
  post('/api/v2/terminal', { agente: a.id }).then(function (r) {
    var d = dondeTerminal(r.donde), t;
    if (r.donde && r.donde.ventana) t = r.estado === 'ya' ? 'Su terminal ya está abierta en otra ventana. Búscala en la barra de tareas.'
      : 'Abrí su terminal en una ventana nueva.';
    else if (r.estado === 'enfocada') t = 'La enfoqué en el hub' + (d ? ': ' + d : '') + '.';
    else if (r.estado === 'ya') t = 'Su terminal ya está abierta en el hub' + (d ? ': ' + d : '') + '. No pude enfocarla; búscala ahí.';
    else t = 'Abriendo su terminal en el hub' + (d ? ': ' + d : '') + '…';
    nota(t, false, NOTA_TERMINAL_MS); if (alDecir) alDecir(t);
    if (b) b.disabled = false; acelerar();
  }, function (e) { nota(e.message, true); if (alDecir) alDecir(e.message); if (b) b.disabled = false; });
}
/* «Cerrar esa terminal» (tu mensaje no salió porque su terminal está abierta): la cierra sin teclear, solo si está
   quieta. Su conversación sigue: la tarjeta queda con «Reenviar», que la retoma desde aquí. */
function cerrarTerminal(a, b, e) {
  if (b) b.disabled = true;
  post('/api/v2/terminal/cerrar', { agente: a.id }).then(function (r) {
    if (r.libre && L(a).noSalio === e) L(a).noSalio = dict(e, { terminal: false, cerrable: false, donde: '', motivo: 'Su terminal ya está cerrada: reenvíalo y sigue aquí.' });
    nota(r.libre ? 'Cerré su terminal' : 'Cerré su terminal, pero su conversación sigue abierta en otra', !r.libre);
    if (b) b.disabled = false; pintarHilo(); pintarRiel(); acelerar();
  }, function (x) { nota(x.message, true); if (b) b.disabled = false; });
}
function chipsFila(defs) {
  var w = el('div', 'chips');
  defs.forEach(function (d) { var b = el('button', 'chip' + (d.p ? ' p' : ''), d.t); if (d.off) b.disabled = true; if (d.title) b.title = d.title; b.onclick = function (e) { e.stopPropagation(); d.run(b); }; w.appendChild(b); });
  return w;
}
var TXT_COLA = { enviando: 'Enviando', recibido: 'Lo recibió; por empezar', pensando: 'Pensando', escribiendo: 'Escribiendo' };   // el «En cola» va en su burbuja
function pz() { var w = el('div', 'pz'); for (var i = 0; i < arguments.length; i++) w.appendChild(arguments[i]); return w; }
var MOTIVO_COLA = { trabajando: 'sale cuando termine lo que está haciendo', detras: 'va después de los anteriores', abriendo: 'sale después del anterior, en cuanto abra', '': 'en camino' };
/* B12: el mensaje que está abriendo su motor (lo dice el servidor: también tras recargar), hasta que sale */
function burbujaAbriendo(a, e) {
  var g = el('div', 'grupo yo'); g.appendChild(texto(el('div', 'm yo pend'), e.texto));
  g.appendChild(el('div', 'herr', 'Abriendo ' + motorN(motorChat(a)) + '… sale en cuanto abra')); return g;
}
/* lo que espera más de un minuto dice cuánto lleva (en minutos: se repinta al cambiar de minuto) */
function llevaCola(desde, ahora) {
  var s = ahora - desde; if (!desde || s < 60) return '';
  var m = Math.floor(s / 60); return 'lleva ' + (m < 60 ? m + ' min' : Math.floor(m / 60) + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : ''));
}
/* en cola mientras trabaja: sale sola al terminar; la salida es «Quitar» */
function burbujaEnCola(a, e) {
  var g = el('div', 'grupo yo'), lleva = llevaCola(e.desde, Date.now() / 1000);
  var h = el('div', 'herr', 'En cola · ' + (lleva ? lleva + ' · ' : '') + (MOTIVO_COLA[e.motivo] || MOTIVO_COLA['']));
  function quitar(b) { b.disabled = true; post('/api/v2/quitar', { agente: a.id, cid: e.id }).then(function () { if (L(a).pendiente && L(a).pendiente.cid === e.id) L(a).pendiente = null; acelerar(); }, function (x) { b.disabled = false; nota(x.message, true); }); }
  g.appendChild(texto(el('div', 'm yo pend'), e.texto)); g.appendChild(h);
  var q = el('button', 'quitar', 'Quitar'); q.title = 'Quitarlo de la cola: no se le manda'; q.onclick = function () { quitar(q); };
  h.appendChild(document.createTextNode(' · ')); h.appendChild(q); return g;
}
function llenarCola(w, a) {
  var l = L(a), p = S.pant[a.id], f = fotoDe(a), slug = slugChat(a), piezas = [], cola = f.cola || [];
  /* lo que mandaste: la cola del servidor (en orden, con por qué espera) y, hasta que el servidor lo ve, lo tuyo */
  var ahora = Date.now() / 1000, minuto = Infinity, ab = f.abriendo;
  if (ab && !(l.pendiente && l.pendiente.cid === ab.id) && !cola.some(function (e) { return e.id === ab.id; }))
    piezas.push({ k: 'abre|' + ab.id, f: firma(ab.texto), hacer: function () { return burbujaAbriendo(a, ab); } });
  cola.forEach(function (e) {
    piezas.push({ k: 'cola|' + e.id, f: firma([e.texto, e.motivo, e.salida ? e.caja : '', llevaCola(e.desde, ahora)].join('|')), hacer: function () { return burbujaEnCola(a, e); } });
    if (e.desde) minuto = Math.min(minuto, 60 - Math.max(0, ahora - e.desde) % 60);
  });
  clearTimeout(w._lleva); if (minuto < Infinity) w._lleva = setTimeout(pintarEstadoVivo, minuto * 1000 + 200);
  if (l.pendiente && !cola.some(function (e) { return e.id === l.pendiente.cid; })) piezas.push({ k: 'pend', f: firma(l.pendiente.texto), hacer: function () { return texto(el('div', 'm yo pend'), l.pendiente.texto); } });
  /* Amigable: tu mensaje espera a que Workspace arregle su motor (sale solo); si ya estaba en la conversación, no se repite */
  var pa = f.por_arreglar;
  if (pa && !pa.ya) piezas.push({ k: 'porarr', f: firma(pa.texto), hacer: function () {
    var g = el('div', 'grupo yo'); g.appendChild(texto(el('div', 'm yo pend'), pa.texto)); g.appendChild(el('div', 'herr', 'Sale solo en cuanto su motor esté listo')); return g;
  } });
  if (f.estado === 'cerrado') piezas.push({ k: 'cerrado', f: firma(f.motor + f.desde), hacer: function () { return tarjetaCerrado(a, f); } });
  if (l.noSalio) piezas.push({ k: 'nosalio|' + l.noSalio.id, f: firma(JSON.stringify(l.noSalio)), hacer: function () { return tarjetaNoSalio(a, l.noSalio); } });
  if (l.reenviar) piezas.push({ k: 'reenv', f: firma(l.reenviar.texto), hacer: function () {
    return pz(el('div', 'aviso', 'Está trabajando; tu mensaje no se mandó para no interrumpirlo.'),
      chipsFila([{ t: 'Enviar igual', p: true, run: function () { var t = l.reenviar.texto, c = l.reenviar.cid; l.reenviar = null; mandar(t, true, c); } }, { t: 'Esperar', run: function () { $('#ta').value = l.reenviar.texto; l.reenviar = null; pintarEstadoVivo(); pintarSend(); } }]));
  } });
  if (l.skillPend) piezas.push({ k: 'skp', f: firma(l.skillPend.skill), hacer: function () {
    var av = el('div', 'aviso'); av.appendChild(svg('skill')); var t1 = el('span'); t1.appendChild(document.createTextNode('Activaste la skill ')); t1.appendChild(el('b', null, l.skillPend.skill)); av.appendChild(t1);
    return pz(av, el('div', 'm ag', 'Lista «' + l.skillPend.skill + '». ¿Arranco ya, o primero me cuentas algo?'),
      chipsFila([{ t: 'Empezar', p: true, run: function (b) { b.disabled = true; arrancarSkill(a, l.skillPend.skill, ''); } }, { t: 'Antes te cuento algo', run: function () { $('#ta').focus(); } }, { t: 'Cancelar', run: function () { l.skillPend = null; pintar(); } }]));
  } });
  /* los permisos que ya contestaste en este turno (al terminar, quedan con su respuesta en la conversación) */
  (f.resueltos || []).forEach(function (p, i) { piezas.push({ k: 'resuelto|' + i, f: firma(JSON.stringify(p)), hacer: function () { return tarjetaPermisoResuelto(p); } }); });
  /* lo que escribe en vivo (llega por la capa de control; se guarda al terminar el turno) */
  if (f.parcial || (f.archivos || []).length) piezas.push({ k: 'parcial', f: firma(f.parcial + JSON.stringify(f.archivos || [])), hacer: function () { return burbuja(a, { rol: 'agente', texto: f.parcial, archivos: f.archivos }); } });
  (l.finesVivos || []).forEach(function (e) { var pf = piezaFin(a, e); piezas.push({ k: 'vivo|' + pf.k, f: pf.f, hacer: pf.hacer }); });
  if (f.permiso) piezas.push({ k: 'permiso|' + (f.permiso.id || 't'), f: firma(JSON.stringify(f.permiso)), hacer: function () { return tarjetaPermiso(a, f.permiso); } });
  /* H4-a: una sesión de otra pestaña que sigue abierta en su terminal: escríbele ahí, o ciérrala para seguir aquí */
  if (tabDe(a) !== NAV && f.terminal && !f.solo_mirar) piezas.push({ k: 'tab-terminal', f: '1', quieto: true, hacer: function () {
    return pz(el('div', 'aviso terminal-ab', '↗ También está abierta en su terminal: escríbele ahí, o ciérrala para seguir aquí.'),
      chipsFila([{ t: 'Ir a la terminal ↗', p: true, run: function (b) { irTerminal(a, b); } }]));
  } });
  /* sin vía oficial que funcione: solo mirar, y su terminal a un toque */
  if (f.solo_mirar) piezas.push({ k: 'solo', f: firma(f.solo_mirar), hacer: function () {
    return pz(el('div', 'aviso', f.solo_mirar + ' Desde aquí solo se mira.'), chipsFila([{ t: 'Ir a la terminal', p: true, run: function (b) { irTerminal(a, b); } }]));
  } });
  if (l.skillOtra) piezas.push({ k: 'skillOtra', f: firma(l.skillOtra.razon + l.skillOtra.nombre), hacer: function () { return piezaSkillOtra(a); } });
  var dy = l.detenerY;
  if (dy) piezas.push({ k: 'detenerY', f: firma(dy.que + !!dy.tarde + !!dy.atorado), hacer: function () {
    var e = el('div', 'estado'); e.appendChild(monitoDe('estado', a, 22));
    e.appendChild(el('span', null, dy.atorado ? 'Te está preguntando algo en su terminal: así no se detiene.' : 'Deteniéndolo para ' + dy.que + '…'));
    var acts = [{ t: 'Cancelar', run: function () { l.detenerY = null; pintarEstadoVivo(); } }];
    if (dy.tarde && dy.cerrar) acts.unshift({ t: (dy.atorado ? '' : 'No se detiene · ') + 'Cerrar y ' + dy.que, p: true, run: function () { l.detenerY = null; dy.cerrar(); } });
    return pz(e, chipsFila(acts));
  } });
  if (dy && !dy.tarde) { clearTimeout(w._dy); w._dy = setTimeout(function () { revisarDetenerY(a); }, DETENER_ESPERA_MS + 200); }
  var cm = cambioDe(a);
  if (cm) {
    var tarde = Date.now() / 1000 - (cm.inicio || cm.t) > (cm.normal || NORMAL_CAMBIO_S);
    piezas.push({ k: 'cambio', f: firma(JSON.stringify(cm) + tarde + L(a).paciencia), hacer: function () { return piezaCambio(a, cm); } });
    if (cm.paso !== 'listo' && cm.paso !== 'error' && !tarde) { clearTimeout(w._tarde); w._tarde = setTimeout(pintarEstadoVivo, ((cm.inicio || cm.t) + (cm.normal || NORMAL_CAMBIO_S)) * 1000 - Date.now() + 200); }
  }
  var err = errorDe(a), ar = f.arreglo;
  /* la página para gente que no sabe de terminal: si se sabe qué le pasa a su motor, su tarjeta en simple (con lo
     que Workspace está arreglando); si no, la de siempre */
  if (err && err.estado) piezas.push({ k: 'ami', f: firma(JSON.stringify([err.estado, err.texto, err.alternativa, ar])), hacer: function () { return tarjetaAmigable(a, err, ar); } });
  else if (err) piezas.push({ k: 'err', f: firma(err.tipo + err.texto), hacer: function () { return tarjetaError(a, err); } });
  else if (ar && ar.paso === 'listo') piezas.push({ k: 'ami-listo', f: firma(JSON.stringify(ar)), hacer: function () { return piezaArreglo(a, ar); } });
  /* Codex sin la confianza de sus hooks (D6-a): su tarjeta, con la guía de /hooks (52_amigable.js) */
  if (confianzaVisible(a, f, err)) piezas.push({ k: 'ami-conf', f: firma(JSON.stringify([f.confianza, ar])), hacer: function () { return tarjetaConfianza(a, f.confianza, ar); } });
  if (f.aviso) piezas.push({ k: 'ami-av', f: firma(JSON.stringify(f.aviso)), hacer: function () { return piezaAvisoAmigable(a, f.aviso); } });
  /* lo que una skill te pregunta (MCP núcleo · preguntar). Skills v11: se contesta en la caja de abajo (55_caja.js); en
     el chat queda una línea ligera «te preguntó» y, al contestar, tu respuesta como burbuja. La de su terminal (con su
     formulario) sigue siendo la tarjeta con «Ir a la terminal» */
  var qp = preguntaDe(a), rl = l.resp;
  if (f.pregunta && f.pregunta.en_terminal) piezas.push({ k: 'pregunta|' + f.pregunta.id, f: firma(JSON.stringify(f.pregunta)), hacer: function () { return tarjetaPreguntaSkill(a, f.pregunta); } });
  else if (qp) piezas.push({ k: 'preg|' + qp.id, f: firma(qp.pregunta + a.c + a.f), hacer: function () { return lineaPregunta(a, qp.pregunta, qp.id); } });
  if (rl && !respuestaEnHistorial(a, rl)) piezas.push({ k: 'resp|' + rl.id, f: firma(rl.q + rl.t), quieto: true, hacer: function () { return respuestaPregunta(a, rl.q, rl.t, rl.id, true); } });
  else if (rl && !(f.pregunta && f.pregunta.id === rl.id)) l.resp = null;     // ya está en la conversación y el servidor ya no la pregunta
  /* la revisión de skills que espera: «Hacer ahora» se la manda por la capa de control */
  if (f.revision && !(p && p.trabajando)) piezas.push({ k: 'revision', f: firma(JSON.stringify(f.revision)), hacer: function () { return piezaRevision(a, f.revision); } });
  var k = actividadDe(a).k;
  /* el estado con nombre, el mismo de la barra y del panel (lo da el servidor); con lo que dice que hace */
  if (((p && p.trabajando) || TXT_COLA[k]) && !f.permiso && !cambiando(a) && !(k === 'enviando' && cola.length)) {
    var subs = p && p.subagentes && p.subagentes.lista && p.subagentes.lista.length, puedeParar = !!(p && p.trabajando);
    var txt = (f.tarea && p && p.trabajando ? f.tarea : (TXT_COLA[k] || 'Pensando')) + (subs ? ' · con ' + subs + (subs === 1 ? ' ayudante' : ' ayudantes') : '') + '…';
    piezas.push({ k: 'estado', f: firma(txt + puedeParar), hacer: function () {
      var e = el('div', 'estado'); e.appendChild(monitoDe('estado', a, 22)); e.appendChild(el('span', null, txt));
      if (puedeParar) { var st = el('button', 'parar'); st.appendChild(icono('stop')); st.title = 'Pedirle que pare'; st.onclick = function () { parar(a).then(function (r) { if (r) nota(r.en_su_terminal ? 'Está trabajando en su terminal: páralo ahí.' : 'Le pedí que pare'); }); }; e.appendChild(st); }
      return e;
    } });
  }
  reconciliar(w, piezas, a.id);
}
/* ---------- cuando su motor falla: decirlo en simple y ofrecer qué hacer ---------- */
var ERR_TXT = {
  limite: ['{m} llegó al límite de tu plan', 'Puedes seguir con otro motor en esta misma conversación, o esperar a que se renueve.'],
  creditos: ['{m} se quedó sin crédito', 'Recarga tu cuenta de {m}, o sigue con otro motor en esta misma conversación.'],
  login: ['{m} necesita que vuelvas a iniciar sesión', 'Entra de nuevo a tu cuenta: te abro su ventana oficial y te guío paso a paso. O sigue con otro motor.'],
  llave: ['La llave del proveedor de {m} venció o no es válida', 'Pon una nueva en su ventana oficial de cuenta: te la abro y te guío paso a paso. O sigue con otro motor.'],
  sobrecarga: ['Los servidores de {m} están saturados', 'Suele pasar en minutos. Reintenta, o sigue con otro motor.'],
  velocidad: ['{m} pidió esperar unos segundos', 'Le llegaron demasiadas peticiones seguidas. Reintenta en un momento.'],
  red: ['No hay conexión con {m}', 'Revisa tu internet y reintenta.']
};
function ultimoMio(a) { var c = S.conv[a.id], t = (c && c.turnos) || []; for (var i = t.length - 1; i >= 0; i--) if (t[i].rol === 'yo' && !esInstruccionSkill(t[i])) return t[i].texto; return ''; }
/* el motor es el de la pantalla que enseña el error (N5: durante un cambio, el de su chat todavía es el de antes) */
function tarjetaError(a, e) {
  var m = motorN(e.motor || motorChat(a)), tx = ERR_TXT[e.tipo] || ['{m} tuvo un problema', 'Reintenta, o sigue con otro motor.'];
  var c = el('div', 'error-c'), ic = el('span', 'ei', '!'); c.appendChild(ic);
  var t = el('div', 'tx'); t.appendChild(el('b', null, tx[0].replace('{m}', m))); t.appendChild(el('small', null, tx[1].replace(/\{m\}/g, m)));
  var det = el('div', 'det', e.texto); t.appendChild(det); c.appendChild(t);
  var acts = [];
  if (/^(sobrecarga|velocidad|red|limite)$/.test(e.tipo) && e.cid) acts.push({ t: 'Reintentar', p: e.tipo !== 'limite', run: function (b) { amiArreglar(a, 'reintentar', b); } });
  if (e.tipo !== 'velocidad' && e.tipo !== 'red') acts.push({ t: 'Seguir con otro motor', p: e.tipo === 'limite' || e.tipo === 'creditos', run: function (b) { menuMotor(b, a); } });
  /* sesión o llave: su ventana oficial de cuenta (la misma de la tarjeta en simple, con su guía): /api/v2/arreglar */
  if (e.tipo === 'login' || e.tipo === 'llave') acts.unshift({ t: e.tipo === 'llave' ? 'Poner una llave nueva' : 'Entrar a mi cuenta', p: true, run: function (b) { amiArreglar(a, 'iniciar_sesion', b); } });
  acts.push({ t: 'Cerrar', run: function () { L(a).errCerrado = e.texto; pintarEstadoVivo(); pintarRiel(); } });
  return pz(c, chipsFila(acts));
}
/* ---------- su motor se cerró (salió a la shell) o tu mensaje no salió: el estado tiene nombre y salida ---------- */
function tarjetaCerrado(a, f) {
  var m = motorN(f.motor || motorChat(a)), c = el('div', 'error-c'); c.appendChild(el('span', 'ei', '!'));
  var t = el('div', 'tx'); t.appendChild(el('b', null, m + ' se cerró')); t.appendChild(el('small', null, 'Lo hablado sigue aquí; tu próximo mensaje lo vuelve a abrir.')); c.appendChild(t);
  return pz(c, chipsFila([{ t: 'Ir a la terminal', run: function (b) { irTerminal(a, b); } }, { t: 'Seguir con otro motor', run: function (b) { menuMotor(b, a); } }]));
}
/* tu mensaje no salió (lo dice la capa de control: su terminal abierta, el motor no abrió…). Si su motor no contestó
   en un minuto (`tarde`) o todavía abre para el anterior (`abriendo`): «Reintentar» con el MISMO id (si al final había
   salido, no se repite) y seguir con otro motor */
function tarjetaNoSalio(a, e) {
  var c = el('div', 'error-c'); c.appendChild(el('span', 'ei', '!'));
  var t = el('div', 'tx'); t.appendChild(el('b', null, 'Tu mensaje no salió')); t.appendChild(el('small', null, e.motivo || 'Su motor no lo aceptó.'));
  /* B12: cuál fue (con varios seguidos no se sabía) */
  if (e.texto) t.appendChild(el('div', 'det', '«' + (e.texto.length > 120 ? e.texto.slice(0, 117) + '…' : e.texto) + '»'));
  if (e.donde) t.appendChild(el('div', 'det', e.donde));       /* dónde está su terminal (lo dijo «Ir a la terminal») */
  c.appendChild(t);
  var original = (L(a).enviados || {})[e.id], acts = [], colgado = e.tarde || e.abriendo;
  if (e.terminal) acts.push({ t: 'Ir a la terminal', p: true, run: function (b) { irTerminal(a, b, function (x) {
    if (L(a).noSalio === e) { L(a).noSalio = dict(e, { donde: x }); pintarHilo(); pintarRiel(); } }); } });
  if (e.terminal && e.cerrable) acts.push({ t: 'Cerrar esa terminal', run: function (b) { cerrarTerminal(a, b, e); } });
  if (original && colgado) acts.push({ t: 'Reintentar', p: true, run: function () { L(a).noSalio = null; mandar(original, true, e.id); } });
  else if (original) acts.push({ t: 'Reenviar', p: !e.terminal, run: function () { L(a).noSalio = null; mandar(original); } });
  if (colgado) acts.push({ t: 'Seguir con otro motor', run: function (b) { menuMotor(b, a); } });
  acts.push({ t: 'Cerrar', run: function () { L(a).noSalio = null; pintarEstadoVivo(); pintarRiel(); } });
  return pz(c, chipsFila(acts));
}
/* ---------- cambiar de motor: un estado con nombre, la caja en pausa mientras, y una salida si tarda ---------- */
function cambioDe(a) {
  var s = fotoDe(a).cambio, l = L(a).cambio;
  if (s && l && s.t + 1 < l.t) s = null;                     // el del servidor es de un cambio anterior
  var x = s || l;
  if (!x || (x.t && L(a).cambioCerrado === x.t)) return null;
  if (x.paso === 'listo' && Date.now() / 1000 - x.t > 8) return null;
  if (!s && Date.now() / 1000 - l.t > 30) return null;        // nunca llegó del servidor: no se queda colgado
  return x;
}
function cambiando(a) { var x = cambioDe(a); return !!(x && x.paso !== 'listo' && x.paso !== 'error'); }
var NORMAL_CAMBIO_S = 30;
function piezaCambio(a, x) {
  var m = motorN(x.motor), de = x.de ? motorN(x.de) : '';
  var volver = x.de && x.de !== x.motor ? { t: 'Volver a ' + de, run: function () { cambiarMotorChat(a, NAV, { id: x.de, nombre: de }, true); } } : null;
  if (x.paso === 'error') {
    var c = el('div', 'error-c'); c.appendChild(el('span', 'ei', '!'));
    var t = el('div', 'tx'); t.appendChild(el('b', null, x.reabre ? 'No pude reabrir su conversación' : 'No pude cambiar a ' + m)); t.appendChild(el('small', null, x.error || 'Algo falló al abrirlo.')); c.appendChild(t);
    var acts = []; if (volver) acts.push(dict(volver, { p: true }));
    acts.push({ t: 'Cerrar', run: function () { L(a).cambioCerrado = x.t; L(a).cambio = null; pintarEstadoVivo(); pintarCaja(); } });
    return pz(c, chipsFila(acts));
  }
  if (x.paso === 'listo') { var lc = el('div', 'listo-c'); lc.appendChild(el('i')); lc.appendChild(el('span', null, 'Listo con ' + m)); return lc; }
  var e = el('div', 'estado'); e.appendChild(monitoDe('estado', a, 22));
  e.appendChild(el('span', null, x.paso === 'guardando' && de ? 'Guardando lo hablado con ' + de + '…' : (x.reabre ? 'Reabriendo a ' : 'Cargando a ') + a.n + ' en ' + m + ' · identidad y memoria…'));
  var tarde = Date.now() / 1000 - (x.inicio || x.t) > (x.normal || NORMAL_CAMBIO_S) && L(a).paciencia !== (x.id || x.t);
  if (!tarde) return pz(e, el('div', 'herr', 'Puedes leer la conversación; para escribir, espera a que quede listo.'));
  var b = [{ t: 'Seguir esperando', run: function () { L(a).paciencia = x.id || x.t; pintarEstadoVivo(); } }];
  if (volver) b.push(volver);
  return pz(e, el('div', 'herr', 'Está tardando más de lo normal.'), chipsFila(b));
}
function dict(o, mas) { var r = {}; for (var k in o) r[k] = o[k]; for (var j in mas) r[j] = mas[j]; return r; }
/* la caja: en pausa (y por qué) mientras no se le puede escribir */
function pausaDe(a) {
  var x = cambioDe(a);
  if (x && x.paso !== 'listo' && x.paso !== 'error') return 'Espera: cargando a ' + a.n + ' en ' + motorN(x.motor) + '…';
  if (L(a).enviando) return 'Espera: abriendo su conversación…';
  if (fotoDe(a).solo_mirar) return 'Solo mirar: escríbele en su terminal';
  return '';
}
function pintarCaja() {
  var a = activo(), ta = $('#ta'), r = a ? pausaDe(a) : '', B = $('.box');
  if (ta.disabled !== !!r) { ta.disabled = !!r; if (B) B.classList.toggle('pausa', !!r); if (!r && document.activeElement === document.body) ta.focus(); }
  ta.placeholder = r || (a && modoCaja(a) === 'abierta' ? 'Escribe tu respuesta…' : placeholderDe(a));
  pintarComposer(true);
}
function pideDe(a) { var e = ejecVigente(a); return e && e.estado === 'pide' ? e : null; }
function placeholderDe(a) { var pe = a && pideDe(a); return !a ? '' : L(a).skillPend ? 'Cuéntale lo que deba saber; al enviarlo arranca' : pe ? 'Responde a ' + pe.skill + '…' : 'Escríbele a ' + a.n + '…   / para usar una skill'; }
/* Detener: por la capa de control de su motor (parar), nunca una tecla */
function parar(a) { return post('/api/v2/parar', { agente: a.id }).then(function (r) { acelerar(); return r || {}; }, function (e) { nota(e.message, true); return null; }); }

/* ---------- mandar ---------- */
/* el id de cada envío: el servidor no teclea dos veces el mismo (doble clic, otra pestaña, un reintento) */
function nuevoCid() { return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
/* lo más que espera la página a que su motor acepte un mensaje (el tope de verdad lo pone la capa de control) */
var MANDAR_TOPE_MS = 60000;
function limpiarCaja() { var t = $('#ta'); t.value = ''; t.style.height = 'auto'; pintarSend(); }
function mandar(t, forzar, cid) {
  var a = activo(); if (!a) return;
  if (adjuntosPendientes()) return nota('Espera a que terminen de subir tus archivos');
  var crudo = (t || '').trim(), adjs = ADJ.slice();
  t = conAdjuntos(crudo); if (!t) return;
  var l = L(a);
  /* si algo falla, lo escrito vuelve a SU agente, sin pisar lo que ya hayas escrito después */
  function devolver() {
    if (S.act === a.id) { var ta = $('#ta'); if (!ta.value.trim()) ta.value = crudo; if (!ADJ.length) { ADJ = adjs; pintarAdjuntos(); } pintarSend(); }
    else { if (!(l.borrador || '').trim()) l.borrador = crudo; if (!(l.adj || []).length) l.adj = adjs; }
  }
  if (l.enviando) return nota('Espera: todavía se está abriendo su conversación');
  if (cambiando(a)) return nota('Espera: está cambiando de motor');
  limpiarCaja(); limpiarAdjuntos();
  if (l.skillPend) return arrancarSkill(a, l.skillPend.skill, t, devolver);
  var slug = NAV, cv = S.conv[a.id] || {}, primera = !slugChat(a);
  /* la pestaña donde lo escribiste: el reintento va ahí aunque ya veas otra (cada conversación guarda sus envíos) */
  var tab = tabDe(a);
  cid = cid || nuevoCid();
  (l.enviados = l.enviados || {})[cid] = t;
  l.pendiente = { texto: t, ts: Date.now(), slug: slug, base: baseDe(cv, slug), cid: cid }; l.reenviar = null; l.noSalio = null; pintarHilo(); pintarRiel(); pintarTop();
  /* sale por la capa de control de su motor: si está trabajando, el servidor lo pone en cola y sale al terminar */
  function intento(otraVez) {
    /* si no contesta en un minuto (su motor no abrió), no se queda en «Enviando…»: la tarjeta con «Reintentar» y la
       caja libre. Se corta la espera (no ocupa una conexión); si al final sale, la tarjeta se va sola */
    var corte = typeof AbortController === 'function' ? new AbortController() : null, vencido = false;
    var reloj = setTimeout(function () {
      vencido = true; if (corte) corte.abort();
      var pe = l.pendiente && l.pendiente.cid === cid ? l.pendiente : null; if (pe) l.pendiente = null;
      l.noSalio = { id: cid, tarde: true, texto: t, slug: slug, base: pe ? pe.base : baseDe(S.conv[a.id], slug),
        motivo: motorN(motorChat(a)) + ' no contestó en un minuto: puede que no haya abierto.' };
      pintarHilo(); pintarRiel(); pintarCaja();
    }, MANDAR_TOPE_MS);
    post('/api/v2/mandar', { agente: a.id, texto: t, cid: cid, tab: tab }, corte && corte.signal).then(function (r) {
      clearTimeout(reloj); if (vencido) return;
      /* un reintento de lo que ya había salido: el servidor no lo repite y ya está en su conversación */
      if (r && r.repetido && l.pendiente && l.pendiente.cid === cid) { l.pendiente = null; pintarHilo(); pintarRiel(); }
      if (primera) cargarPestanas(); acelerar();
    }, function (e) {
      clearTimeout(reloj); if (vencido) return;
      /* sin respuesta (la red): una vez más con el MISMO id; si ya había llegado, el servidor no lo repite */
      if (e.status === undefined && !otraVez) return setTimeout(function () { intento(true); }, 1000);
      if (l.pendiente && l.pendiente.cid === cid) l.pendiente = null;   /* B12: solo el suyo (no el de otro envío) */
      var d = e.datos || {};
      /* Amigable: su motor tiene algo que Workspace explica (y arregla si puede): lo dice su tarjeta y tu mensaje
         sale solo al arreglarse; no hay otra tarjeta de «no salió» */
      if (e.status === 409 && d.amigable) acelerar();
      else if (e.status === 409) l.noSalio = { id: cid, motivo: e.message, terminal: !!d.terminal, cerrable: !!d.cerrable, abriendo: !!d.abriendo, texto: t };
      else { nota(e.message, true); devolver(); }
      pintarHilo(); pintarRiel();
    });
  }
  intento(false);
}

/* ---------- la caja: Enter manda, «/» busca una skill, «+» trae las fijadas ---------- */
var SLASH = null;
function slash() {
  var v = $('#ta').value, a = activo();
  if (!a || v.charAt(0) !== '/') { if (SLASH) { SLASH = null; cerrarCapas(); } return; }
  var q = v.slice(1).trim().toLowerCase();
  /* gana el nombre: primero las que empiezan así, luego las que lo traen en el nombre, al final por su descripción (F17) */
  var rango = function (s) { var n = s.nombre.toLowerCase(); return !q ? 0 : n.indexOf(q) === 0 ? 0 : n.indexOf(q) >= 0 ? 1 : 2; };
  SLASH = skillsDe(a).filter(function (s) { return !q || s.nombre.toLowerCase().indexOf(q) >= 0 || (s.descripcion || '').toLowerCase().indexOf(q) >= 0; })
    .sort(function (x, y) { return rango(x) - rango(y); }).slice(0, 12);
  var filas = SLASH.length ? SLASH.map(function (s) { return { t: s.nombre, sub: s.categoria || '', run: function () { $('#ta').value = ''; SLASH = null; pintarSend(); activarSkill(a, s.nombre); } }; }) : [{ t: q ? 'Ninguna skill con «' + q + '»' : 'Este agente no tiene skills todavía', off: true }];
  pop($('.box'), filas, 'Skills · Enter usa la primera', true);
}
function menuMas() {
  var a = activo(); if (!a) return;
  var filas = [{ t: 'Adjuntar archivos', sub: 'o suéltalos aquí', run: function () { $('#fileIn').click(); } }, '-'], fijas = skillsDe(a).filter(function (s) { return a.fijas.indexOf(s.nombre) >= 0; });
  fijas.forEach(function (s) { filas.push({ t: s.nombre, sub: '★ skill', run: function () { activarSkill(a, s.nombre); } }); });
  if (fijas.length) filas.push('-');
  filas.push({ t: 'Todas las skills', sub: 'o escribe /', run: function () { abrirPanel('skills'); } });
  pop($('#mas'), filas, null, true);
}
