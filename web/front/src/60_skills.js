/* ================= skills: se buscan y activan en el panel, se viven en el chat ================= */
/* con movimiento reducido no hay vuelos, latidos ni monito que camina: los estados cambian sin animación */
var MOV = !(typeof window !== 'undefined' && window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
function activarSkill(a, nombre) {
  /* skills v11: una por agente; «Usar» (o «/skill») la arranca y su proceso se abre a la derecha */
  if (S.act !== a.id) elegirAgente(a.id);
  if (tabDe(a) !== NAV) elegirTab(a, NAV);      // H4-a: las skills corren en su conversación de siempre
  var r = corrida(a);
  if (r && ABIERTA[r.estado]) { nota('Ya corre «' + nombreSkill(r.skill) + '». Detenla o espera a que termine.'); var an = anclaDe(LUGAR); if (an) sacudir(an); return; }
  var oc = ocupadoDe(a); if (oc) return nota(oc);
  cerrarHoja(); usarSkill(a, nombre, null);
}
function arrancarSkill(a, nombre, textoExtra, devolver) {
  /* siempre en SU conversación: su instrucción sale por la capa de control (si está trabajando, en cola) */
  var l = L(a), cuerpo = { agente: a.id, skill: nombre };
  if (textoExtra) cuerpo.texto = textoExtra;
  l.skillPend = null; if (!l.arrancando || l.arrancando.skill !== nombre) l.arrancando = { skill: nombre, ts: Date.now() };
  pintar(S.PANEL === 'skills');
  post('/api/v2/skill', cuerpo).then(function () {
    if (!slugChat(a)) cargarPestanas();
    acelerar(30); cargarEjecuciones(a).then(function () { l.arrancando = null; pintar(S.PANEL === 'skills'); });
  }, function (e) { l.arrancando = null; nota(e.message, true); if (devolver) devolver(); pintar(true); });
}
function piezaSkillOtra(a) {
  var o = L(a).skillOtra, v = el('div', 'aviso'); v.appendChild(svg('skill')); v.appendChild(el('span', null, o.razon));
  return pz(v, chipsFila([{ t: 'Detener y empezar la nueva', p: true, run: function () {
    var e = ejecVigente(a); L(a).skillOtra = null;
    if (e) detenerSkill(a, e);
    detenerY(a, 'empezar «' + o.nombre + '»', function () { activarSkill(a, o.nombre); });
  } }, { t: 'Cancelar', run: function () { L(a).skillOtra = null; pintarEstadoVivo(); } }]));
}
function detenerSkill(a, e) {
  var l = L(a); (l.detenidas = l.detenidas || {})[e.id] = 1;
  a.detenidas = (a.detenidas || []).concat([e.id]).slice(-100);
  post('/api/front/prefs', { agente: a.id, detenidas: a.detenidas }).catch(function () {});
  /* skills-cierre: el servidor la deja «pausada» (detenida) y, si su motor trabaja en ella, le pide parar */
  if (!e._arr) post('/api/v2/skill/accion', { agente: a.id, id: e.id, accion: 'detener' }).then(function () { acelerar(20); }, function () { parar(a); });
  nota('Le pedí que pare «' + e.skill + '»'); pintar(S.PANEL === 'skills');
}
/* skills-cierre · la que se detuvo sola (su turno acabó sin «fin», Parar, un error, le escribiste otra cosa) */
function pausadaVisible(a, e) {
  var p = e && e.pausa || {};
  /* la que detuviste tú no se ve; la de «otra cosa» (otro_mensaje) se pausa en silencio: solo su pastilla en la caja */
  if (!e || e.estado !== 'pausada' || p.cerrada || p.motivo === 'detenida' || p.motivo === 'otro_mensaje' || detenida(a, e) || (L(a).cerradas || {})[e.id]) return false;
  var t = Date.parse(e.actualizado || e.creado || '') || 0;
  return !t || Date.now() - t < 6 * 3600 * 1000;
}
function textoPausa(e) {
  var n = (e.pausa || {}).paso || 0;
  return n ? 'Se detuvo en el paso ' + n : 'Se detuvo antes de empezar';
}
function seguirSkill(a, e) {
  post('/api/v2/skill/accion', { agente: a.id, id: e.id, accion: 'seguir' }).then(function () {
    acelerar(30); cargarEjecuciones(a).then(function () { pintar(S.PANEL === 'skills'); });
  }, function (err) { nota(err.message, true); });
}
function cerrarPausada(a, e) {
  (L(a).cerradas = L(a).cerradas || {})[e.id] = 1;
  post('/api/v2/skill/accion', { agente: a.id, id: e.id, accion: 'cerrar' }).catch(function () {});
  pintarPanel(); pintarTop();
}
function subirArchivo(a, e) {
  var inp = el('input'); inp.type = 'file';
  inp.onchange = function () {
    var f = inp.files && inp.files[0]; if (!f) return;
    if (f.size > 15 * 1024 * 1024) return nota('El archivo pasa de 15 MB', true);
    var r = new FileReader();
    r.onload = function () {
      var datos = String(r.result).split(',')[1] || '';
      post('/api/v2/archivo', { agente: a.id, id: e.id, nombre: f.name, datos: datos }).then(function () { nota('Le pasé ' + f.name); acelerar(30); }, function (err) { nota(err.message, true); });
    };
    r.readAsDataURL(f);
  };
  inp.click();
}
/* sus pasos (hecho, el de ahora, lo que sigue) y lo que te pide: lo mismo en la tarjeta, la franja y el panel (F17) */
function detallePasos(c, e) {
  var pasos = e.pasos || [];
  if (pasos.length) {
    var ol = el('ol');
    pasos.forEach(function (p, i) {
      var est = p.estado === 'done' ? 'hecho' : p.estado === 'now' ? (e.estado === 'pide' ? 'pide' : 'ahora') : 'luego';
      var li = el('li', est); li.appendChild(el('i', null, est === 'hecho' ? '✓' : String(i + 1)));
      var sp = el('span', null, p.texto); if (p.nota) sp.title = p.nota; li.appendChild(sp); ol.appendChild(li);
    });
    c.appendChild(ol);
  }
  if (e.estado === 'pide' && e.pide) { var pd = el('div', 'pidebox'); texto(pd, (e.pide.texto || 'Necesita algo de ti para seguir.') + (e.pide.archivo ? '' : '\n\nContéstale en la caja de abajo.')); c.appendChild(pd); }
  return c;
}
/* la tarjeta del pipeline vive en el chat, con el monito y el color de su agente */
function tarjetaSkill(a, e) {
  var vig = ejecVigente(a), viva = vig && vig.id === e.id, n = (e.pasos || []).length, h = pasosHechos(e);
  var fin = e.estado === 'listo', c = el('div', 'sk' + (fin ? ' fin' : ''));
  var hd = el('div', 'hd');
  if (viva || fin) hd.appendChild(monitoDe('tarjeta', a, 30)); else { var ic = el('span', 'ic'); ic.appendChild(svg('skill')); hd.appendChild(ic); }
  hd.appendChild(el('b', null, e.skill));
  hd.appendChild(el('small', null, fin ? 'listo' : e.estado === 'pide' ? 'esperándote' : e.estado === 'arrancando' ? 'arrancando' : n ? 'paso ' + Math.min(n, h + 1) + ' de ' + n : 'armando el plan'));
  c.appendChild(hd);
  var br = el('div', 'barra'), bb = el('b'); bb.style.width = (fin ? 100 : n ? Math.max(4, Math.round(100 * h / n)) : 4) + '%'; br.appendChild(bb); c.appendChild(br);
  detallePasos(c, e);
  if (e.estado === 'pide' && e.pide) {
    var defs = [];                            // se responde en la caja de abajo («Responde a …»): aquí solo lo que no es escribir
    if (e.pide.archivo) defs.push({ t: 'Subir archivo', p: true, run: function () { subirArchivo(a, e); } });
    defs.push({ t: 'Saltar este paso', run: function () { post('/api/v2/mandar', { agente: a.id, texto: 'Sigue sin eso; márcalo en el resultado.', cid: nuevoCid() }).then(function () { acelerar(20); }, function (err) { nota(err.message, true); }); } });
    var ch = chipsFila(defs); ch.style.margin = '0 12px 12px'; c.appendChild(ch);
  }
  if (fin) {
    if (e.resumen) { var r = el('div', 'res'); r.appendChild(svg('doc')); r.appendChild(texto(el('span', 'rt'), e.resumen)); c.appendChild(r); }
    var acc = chipsFila([{ t: 'Repetir', run: function () { activarSkill(a, e.skill); } }]); acc.style.margin = '0 12px 12px'; c.appendChild(acc);
  } else if (viva) {
    var ac2 = chipsFila([{ t: 'Detener', run: function () { detenerSkill(a, e); } }]); ac2.style.margin = '0 12px 12px'; c.appendChild(ac2);
  }
  return c;
}
/* nombre en palabras normales y lo que hizo su última herramienta, en simple */
function nombreSkill(s) {
  return String(s || '').replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^./, function (c) { return c.toUpperCase(); });
}
/* lo que hizo su última herramienta, en simple («Creó notas.html», «Tomó una captura»); '' si no dice nada útil */
var HECHO = { comando: 'Corrió un comando', crear: ['Creó ', 'Creó un archivo'], cambiar: ['Cambió ', 'Cambió un archivo'],
  borrar: ['Borró ', 'Borró un archivo'], imagen: ['Miró ', 'Miró una imagen'], leer: ['Leyó ', 'Leyó un archivo'],
  buscar: 'Buscó en tus archivos', web: 'Abrió una página de internet' };
function hechoEnSimple(h) {
  if (!h || !h.n) return '';
  var pm = { herramienta: h.n, detalle: h.d || '' };
  if (/screenshot|captura|snapshot/i.test(String(h.n))) return 'Tomó una captura';
  /* su clase la dice la capa de control si su vía la sabe (ACP: `c`, B01); si no, por el nombre exacto, sin adivinar */
  var d = permisoDatos(pm), k = h.c && HECHO[h.c] ? h.c : permisoClase(pm, d), f = permisoArchivo(d, pm.detalle, h.f);
  if (k === 'leer' && PERM_IMAGEN.test(f)) k = 'imagen';
  var x = HECHO[k];
  if (!x) return '';
  return typeof x === 'string' ? x : (f ? x[0] + f : x[1]);
}
/* ---------- skills v11 · el proceso a la derecha (P-1) ----------
   Al usar una skill, el panel de skills se cierra y su proceso se abre a la derecha: su nombre, la barra y los pasos en
   el color del agente, una línea en vivo (lo que hace, de sus herramientas en simple), «Lo que va haciendo», el resultado
   y «Qué hace esta skill» plegado. Encima camina su monito. Si abres otro panel, el proceso vuela a la barra sobre la caja
   y regresa al cerrarlo. En el chat solo queda la marca «Empezó…» y, al terminar, la tarjeta «Terminó». */
var PROC = null, BARRA = null, LUGAR = '', CONT = '', CONT_AG = '', VUELO = null, FEED = {};
var ANCHO = { skills: 372, proceso: 352 };
/* resortes de gomita: los mismos que mueven a los monitos */
function muelle(o, meta, k, d, h) { o.v += (k * (meta - o.p) - d * o.v) * h; o.p += o.v * h; }
function curvaResorte(k, d, ms) { var p = 0, v = 0, h = 1 / 120, out = [], n = Math.round(ms / 1000 * 60); for (var i = 0; i <= n; i++) { out.push(p); for (var j = 0; j < 2; j++) { v += (k * (1 - p) - d * v) * h; p += v * h; } } out[n] = 1; return out; }
function curvaGel(k, d, v0, ms) { var g = 0, v = v0, h = 1 / 120, out = [], n = Math.round(ms / 1000 * 60); for (var i = 0; i <= n; i++) { out.push(g); for (var j = 0; j < 2; j++) { v += (-k * g - d * v) * h; g += v * h; } } out[n] = 0; return out; }
function animar(e, ps, fn, o) { if (!MOV) return { cancel: function () {} }; return e.animate(ps.map(fn), { duration: o.ms, easing: 'linear', delay: o.delay || 0, fill: o.fill || 'none' }); }
function resorte(e, fn, o) { o = o || {}; var ms = o.ms || 600; return animar(e, curvaResorte(o.k || 170, o.d || 16, ms), fn, { ms: ms, delay: o.delay, fill: o.fill }); }
function gelear(e, o) {
  o = o || {}; var ms = o.ms || 720, ax = o.ax == null ? .03 : o.ax, ay = o.ay == null ? .06 : o.ay;
  e.style.transformOrigin = o.origen || '50% 100%';
  return animar(e, curvaGel(o.k || 190, o.d || 9, o.v || -13, ms), function (g) { return { transform: 'scale(' + (1 - g * ax).toFixed(4) + ',' + (1 + g * ay).toFixed(4) + ')' }; }, { ms: ms });
}
function sacudir(e) { animar(e, curvaGel(300, 9, 70, 640), function (g) { return { transform: 'translateX(' + (g * 1.6).toFixed(2) + 'px)' }; }, { ms: 640 }); }
function rectDe(e) { var r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }
function ponTexto(e, t) { if (e.textContent === t) return; e.textContent = t; if (MOV) e.animate([{ opacity: 0, transform: 'translateY(5px)' }, { opacity: 1, transform: 'none' }], { duration: 360, easing: 'cubic-bezier(.22,1,.36,1)' }); }
function pegarAbajo(ms) {
  var f = $('#feed'); if (!f || f.scrollHeight - f.scrollTop - f.clientHeight > 90) return;
  var fin = performance.now() + ms; f.style.scrollBehavior = 'auto';
  (function paso() { f.scrollTop = f.scrollHeight; if (performance.now() < fin) requestAnimationFrame(paso); else f.style.scrollBehavior = ''; })();
}
function haceTxt(t) { var d = Math.round((Date.now() - t) / 1000); return d < 1 ? 'ahora' : d < 60 ? 'hace ' + d + ' s' : 'hace ' + Math.round(d / 60) + ' min'; }

/* ---- la corrida que se ve: la que arranca, la vigente o la que terminó mientras la veías (hasta que la cierres) ---- */
function corrida(a) {
  var l = L(a), e = ejecVigente(a);
  if (l.arrancando && (!e || e.skill !== l.arrancando.skill)) return { id: 'arr-' + l.arrancando.ts, skill: l.arrancando.skill, estado: 'arrancando', pasos: [], _arr: true };
  if (e) { (l.vistas = l.vistas || {})[e.id] = 1; return e; }
  var ult = (S.ejec[a.id] || [])[0];
  if (pausadaVisible(a, ult)) return ult;
  return (S.ejec[a.id] || []).filter(function (x) { return x.estado === 'listo' && (l.vistas || {})[x.id] && !(l.cerradas || {})[x.id] && !detenida(a, x); })[0] || null;
}
function lugarProceso(a) { return a && corrida(a) ? (S.PANEL || L(a).mini ? 'barra' : 'panel') : ''; }
function anclaDe(l) { return l === 'panel' ? $('#sideIn .hero3') : l === 'barra' ? $('#activa .pa3:not(.sale)') : null; }
function skillInfo(a, nombre) { return skillsDe(a).filter(function (s) { return s.nombre === nombre; })[0] || {}; }
/* la pregunta de la skill que se contesta en la página (la de su terminal, con su formulario, no) */
function preguntaDe(a) { var q = a && fotoDe(a).pregunta; return q && !q.en_terminal && (L(a).sinPregunta !== q.id) && !(L(a).resp && L(a).resp.id === q.id) ? q : null; }
function progreso(r) { if (r.estado === 'listo') return 1; var n = (r.pasos || []).length; return n ? pasosHechos(r) / n : 0; }
/* «Lo que va haciendo»: lo que vio la página de esta corrida, lo más nuevo arriba (sus herramientas en simple, lo que te
   preguntó y lo que contestaste) */
function feedDe(a, r) {
  var k = r.id, F = FEED[k];
  if (!F) {
    var arr = Object.keys(FEED).filter(function (x) { return x.indexOf('arr-') === 0 && FEED[x].skill === r.skill && FEED[x].ag === a.id; })[0];
    var desde = Date.parse(r.creado || '') || Date.now();
    F = FEED[k] = arr ? FEED[arr] : { ag: a.id, skill: r.skill, desde: desde, xs: [{ txt: 'Empezó «' + nombreSkill(r.skill) + '»', t: desde, nuevo: true }], vistos: {} };
    if (arr) delete FEED[arr];
  }
  var f = fotoDe(a);
  (f.hizo || []).forEach(function (h) {
    var clave = (h.t || 0) + '|' + h.n; if (F.vistos[clave] || (h.t || 0) * 1000 < F.desde - 2000) return; F.vistos[clave] = 1;   // las de antes de empezar, no
    var txt = hechoEnSimple(h); if (txt) F.xs.unshift({ txt: txt, t: (h.t || 0) * 1000 || Date.now(), nuevo: true, f: h.f || '' });
  });
  var q = a && fotoDe(a).pregunta;
  if (q && !q.en_terminal && !F.vistos['q|' + q.id]) { F.vistos['q|' + q.id] = 1; F.xs.unshift({ txt: 'Te preguntó: ' + q.pregunta, t: Date.now(), nuevo: true }); }
  if (r.estado === 'pausada' && !F.vistos['pausa|' + ((r.pausa || {}).desde || '')]) {
    F.vistos['pausa|' + ((r.pausa || {}).desde || '')] = 1;
    var pend = (r.pausa || {}).pendiente;
    F.xs.unshift({ txt: textoPausa(r) + (pend ? ' · quedó pendiente: «' + String(pend).slice(0, 120) + '»' : ''), t: Date.now(), nuevo: true });
  }
  if (r.estado === 'listo' && !F.vistos.fin) { F.vistos.fin = 1; F.xs.unshift({ txt: 'Terminó' + (r.resumen ? ': ' + r.resumen : ''), t: Date.now(), nuevo: true }); }
  F.xs = F.xs.slice(0, 30);
  return F;
}
function ultimoArchivo(F) { var x = F.xs.filter(function (y) { return y.f; })[0]; return x ? x.f : ''; }
function cuatro() { return innerHeight < 860 ? 3 : 4; }

/* ---- el panel de la derecha: skills · agente · proceso, y el vuelo del proceso entre el panel y la barra ---- */
function pintarPanel(o) {
  o = o || {};
  var Sd = $('#side'), a = activo(), lugar = lugarProceso(a), cont = a ? S.PANEL || (lugar === 'panel' ? 'proceso' : '') : '';
  var ae = document.activeElement, foco = ae && ae.classList && ae.classList.contains('sq3') ? ae.value : null;
  if (VUELO) VUELO.fin(true);
  var antes = LUGAR, desde = o.desde || null;
  if (!desde && antes && lugar && antes !== lugar && a && CONT_AG === a.id) { var vj = anclaDe(antes); if (vj) { desde = { r: rectDe(vj), clon: clonar(vj) }; vj.style.visibility = 'hidden'; } }
  Sd.classList.toggle('on', !!cont); Sd.classList.toggle('ancho', cont === 'agente' && !!S.EDIT);
  // «skp», no «sk»: .sk es la tarjeta de la skill en el chat (marco del color del agente)
  Sd.classList.toggle('skp', cont === 'skills'); Sd.classList.toggle('pr', cont === 'proceso');
  if (S.PANEL !== 'skills') cerrarHoja();
  var otro = !!a && CONT_AG !== a.id;                    // otro agente: su panel, no el del de antes
  var nuevo = cont !== CONT || otro || o.forzar || cont === 'agente' || (cont === 'proceso' && !(PROC && PROC.ag === a.id && PROC.w.isConnected && mismaCorrida(PROC, corrida(a))));
  if (nuevo) cambiarIn(cont, a, !!desde && cont === 'proceso', cont !== CONT || otro);
  else if (cont === 'proceso') actualizarProceso(a);
  pintarBarra(a, lugar === 'barra', !!desde);
  CONT = cont; LUGAR = lugar; CONT_AG = a ? a.id : '';
  document.body.classList.toggle('conbarra', lugar === 'barra');
  var destino = anclaDe(lugar);
  if (destino && desde) { destino._final = lugar === 'panel' ? finalHero(destino) : null; morfar(desde, destino, a); }
  else if (destino && destino._nuevo) entrada(destino, lugar);
  if (destino) destino._nuevo = false;
  if (cont === 'skills' && foco !== null) { var q = $('#sideIn .sq3'); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }
  if (a && lugar) actorPrep(a); else decoEvento(null, 'fuera');
}
function mismaCorrida(P, r) { return !!r && P.k === r.skill && (P.id === r.id || P.id.indexOf('arr-') === 0); }
/* el contenido nuevo entra con un resorte y el viejo sale hacia la derecha; mismo contenido (el agente), en su lugar */
function cambiarIn(cont, a, quieto, animado) {
  var Sd = $('#side'), viejo = $('#sideIn');
  AHORA_UPD = null;
  if (viejo && !(animado && MOV)) { viejo.textContent = ''; viejo.style.width = ''; if (cont) llenarIn(viejo, cont, a); else PROC = null; return; }
  if (viejo) {
    viejo.removeAttribute('id'); viejo.style.position = 'absolute'; viejo.style.left = '0'; viejo.style.top = '0'; viejo.style.pointerEvents = 'none';
    viejo.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateX(26px)' }], { duration: 150, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' }).onfinish = function () { viejo.remove(); };
  }
  if (CONT === 'proceso') PROC = null;
  var I = el('div', 'in'); I.id = 'sideIn'; Sd.appendChild(I);
  if (!cont) return;
  llenarIn(I, cont, a);
  resorte(I, function (p) { return { transform: 'translateX(' + (quieto ? 0 : 28 * (1 - p)).toFixed(2) + 'px)', opacity: Math.max(0, Math.min(1, p * 1.6)) }; }, { k: 170, d: 17, ms: 680, delay: viejo ? 160 : 30, fill: 'backwards' });
}
function llenarIn(I, cont, a) {
  if (cont === 'skills') {
    try { return panelSkills(I); } catch (err) {
      /* nunca un panel vacío y mudo: se dice, y el error queda en la consola */
      if (window.console) console.error('panel de skills:', err);
      var v = el('div', 'vacio3'); v.appendChild(el('b', null, 'No pude mostrar sus skills')); v.appendChild(el('span', null, 'Ciérralo y vuelve a abrirlo; si sigue, avísale a quien cuida Workspace.'));
      return I.appendChild(v);
    }
  }
  if (cont === 'proceso') return construirProceso(I, a);
  var x = el('button', 'cb x'); x.appendChild(icono('x')); x.title = 'Cerrar'; x.onclick = function () { abrirPanel(''); }; I.appendChild(x);
  if (S.EDIT) return editor(I);
  panelAgente(I);
}
/* a dónde va a quedar la tarjeta del proceso (el vuelo aterriza ahí, sin perseguirla mientras el panel se desliza) */
function finalHero(h) {
  return function () {
    var Sd = $('#side').getBoundingClientRect(), I = h.closest('.in');
    return { x: Sd.right - ANCHO.proceso + h.offsetLeft, y: Sd.top + h.offsetTop - (I ? I.scrollTop : 0), w: h.offsetWidth, h: h.offsetHeight };
  };
}
/* el clon que vuela: solo la cabecera de la fila, sin el detalle abierto ni estados pasajeros */
function clonar(e, rf) {
  var r = (rf || e).getBoundingClientRect(), c = e.cloneNode(true);
  c.removeAttribute('id'); c.querySelectorAll('[id]').forEach(function (x) { x.removeAttribute('id'); });
  c.querySelectorAll('.det3').forEach(function (x) { x.remove(); });
  c.classList.remove('abierta', 'lanza', 'apretada');
  c.style.cssText += ';position:absolute;left:-1.5px;top:-1.5px;margin:0;width:' + r.width + 'px;height:' + r.height + 'px;background:transparent;border-color:transparent;box-shadow:none;visibility:visible;opacity:1;animation:none;transform:none';
  return c;
}
/* el vuelo: la tarjeta viaja entre la fila, el panel y la barra con resortes (posición k=230 d=26; tamaño k=220 d=24) */
function morfar(desde, destino, a) {
  if (!MOV) { destino.style.visibility = ''; return; }
  var r0 = desde.r, run = corrida(a), fin = run && run.estado === 'listo';
  destino.style.visibility = 'hidden';
  var sh = el('div', 'morfo' + (fin ? ' fin' : '') + (desde.fila ? ' desdeFila' : '')); document.body.appendChild(sh);
  if (desde.clon) { var cw = el('div', 'clon'); cw.appendChild(desde.clon); sh.appendChild(cw); cw.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 110, easing: 'ease-out', fill: 'forwards' }); }
  var cara = el('div', 'cara'); cara.appendChild(el('b', null, nombreSkill(run ? run.skill : ''))); sh.appendChild(cara);
  cara.animate([{ opacity: 0, transform: 'scale(.85)' }, { opacity: 1, transform: 'none' }], { duration: 220, delay: 100, easing: 'cubic-bezier(.34,1.56,.64,1)', fill: 'backwards' });
  if (desde.fila) requestAnimationFrame(function () { sh.classList.remove('desdeFila'); });
  var X = { p: r0.x, v: 0 }, Y = { p: r0.y, v: 0 }, W = { p: r0.w, v: 0 }, H = { p: r0.h, v: 0 };
  var t0 = performance.now(), ult = t0, d0 = 0, raf = 0, listo = false;
  var V = VUELO = { sh: sh, destino: destino, fin: aterrizar };
  function pon(x, y, w, h) { sh.style.left = x.toFixed(1) + 'px'; sh.style.top = y.toFixed(1) + 'px'; sh.style.width = Math.max(24, w).toFixed(1) + 'px'; sh.style.height = Math.max(24, h).toFixed(1) + 'px'; cara.style.top = Math.max(6, Math.min(h / 2 - 15, 14)).toFixed(1) + 'px'; }
  function cuadro(ahora) {
    var dt = Math.min(.034, (ahora - ult) / 1000); ult = ahora;
    var r = destino._final ? destino._final() : rectDe(destino);
    if (!d0) d0 = Math.max(1, Math.hypot(r.x - r0.x, r.y - r0.y));
    for (var i = 0, n = Math.max(1, Math.ceil(dt / .006)), h = dt / n; i < n; i++) { muelle(X, r.x, 230, 26, h); muelle(Y, r.y, 230, 26, h); muelle(W, r.w, 220, 24, h); muelle(H, r.h, 220, 24, h); }
    var q = Math.max(0, Math.min(1, 1 - Math.hypot(r.x - X.p, r.y - Y.p) / d0)), arco = -Math.min(60, d0 * .12) * 4 * q * (1 - q);
    pon(X.p, Y.p + arco, W.p, H.p);
    var quieto = Math.abs(r.x - X.p) < .8 && Math.abs(r.y - Y.p) < .8 && Math.abs(r.w - W.p) < .8 && Math.abs(r.h - H.p) < .8 && Math.abs(X.v) + Math.abs(Y.v) + Math.abs(W.v) + Math.abs(H.v) < 50;
    var cerca = Math.abs(r.x - X.p) < 6 && Math.abs(r.y - Y.p) < 6 && Math.abs(r.w - W.p) < 10 && Math.abs(r.h - H.p) < 26;
    if (((quieto || cerca) && ahora - t0 > 170) || ahora - t0 > 1000) return aterrizar(false);
    raf = requestAnimationFrame(cuadro);
  }
  function aterrizar(ya) {
    if (listo) return; listo = true; cancelAnimationFrame(raf); if (VUELO === V) VUELO = null;
    destino.style.visibility = '';
    if (ya) { sh.remove(); return; }
    var abajo = destino.classList.contains('pa3');
    cara.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 60, easing: 'ease-out', fill: 'forwards' });
    destino.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, delay: 60, easing: 'ease-out', fill: 'backwards' });
    gelear(destino, { origen: abajo ? '50% 100%' : '50% 0%', v: -5, ax: abajo ? .008 : .015, ay: abajo ? .04 : .025, ms: 680 });
    sh.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-out', fill: 'forwards' }).onfinish = function () { sh.remove(); };
    brincaMonito();
  }
  pon(r0.x, r0.y, r0.w, r0.h);
  raf = requestAnimationFrame(cuadro);
}
/* cuando aparece sin venir de otro lado: un brinco de gomita */
function entrada(e, lugar) {
  resorte(e, function (p) { return { transform: 'translateY(' + (10 * (1 - p)).toFixed(2) + 'px) scale(' + (.96 + .04 * p).toFixed(4) + ')', opacity: Math.max(0, Math.min(1, p * 2)) }; }, { k: 200, d: 14, ms: 720, delay: lugar === 'panel' ? 140 : 40, fill: 'backwards' });
  setTimeout(brincaMonito, 380);
}

/* ---- usar una skill: la fila se marca y vuela a la tarjeta del proceso ---- */
function lanzarSkill(a, s, f) {
  var r = corrida(a);
  if (r && ABIERTA[r.estado]) { nota('Ya corre «' + nombreSkill(r.skill) + '». Detenla o espera a que termine.'); var an = anclaDe(LUGAR); if (an) sacudir(an); return; }
  var oc = ocupadoDe(a); if (oc) return nota(oc);
  f.classList.add('lanza');
  setTimeout(function () { usarSkill(a, s.k, f); }, 140);
}
function usarSkill(a, nombre, desdeEl) {
  var l = L(a), r = corrida(a), desde = null;
  if (r && (r.estado === 'listo' || r.estado === 'pausada')) (l.cerradas = l.cerradas || {})[r.id] = 1;
  if (desdeEl && desdeEl.isConnected) { var rf = desdeEl.querySelector('.fila') || desdeEl; desde = { r: rectDe(rf), clon: clonar(desdeEl, rf), fila: true }; desdeEl.style.visibility = 'hidden'; }
  l.mini = false; S.PANEL = ''; S.EDIT = null; l.arrancando = { skill: nombre, ts: Date.now() };
  pintarPanel({ desde: desde }); pintarTop();
  decoEvento(a, 'inicio');
  arrancarSkill(a, nombre, '');
}
function verProceso(a) {
  if (!corrida(a)) return;
  if (LUGAR === 'barra') { S.PANEL = ''; S.EDIT = null; L(a).mini = false; pintarPanel(); pintarTop(); }
  else if (LUGAR === 'panel') { var h = anclaDe('panel'); if (h) gelear(h, { origen: '50% 0%', v: -8, ax: .012, ay: .02 }); brincaMonito(); }
}
function cerrarProceso(a) { var r = corrida(a); if (r && r.estado === 'pausada') return cerrarPausada(a, r); if (r) (L(a).cerradas = L(a).cerradas || {})[r.id] = 1; pintarPanel(); pintarTop(); }
function detenerProceso(a) {
  var r = corrida(a); if (!r) return;
  var q = fotoDe(a).pregunta; if (q) L(a).sinPregunta = q.id;
  if (r._arr) { L(a).arrancando = null; pintarPanel(); return; }
  detenerSkill(a, r); pintarComposer(true);
}

/* ---- la tarjeta del proceso ---- */
function construirProceso(I, a) {
  var r = corrida(a); if (!r) return;
  var info = skillInfo(a, r.skill), w = el('div', 'pr3 p1v'); I.appendChild(w);
  var h = el('div', 'hero3'); h._nuevo = true; w.appendChild(h);
  h.onclick = function (e) { if (e.target.closest('button')) return; verProceso(a); };
  var hd = el('div', 'h5'); hd.appendChild(emblema(info.categoria || '', 16)); var nm = el('b', 'nm5', nombreSkill(r.skill)); nm.title = nombreTema(info.categoria); hd.appendChild(nm);
  var en = el('button', 'ic5'); en.appendChild(ico3('abajo', 16, 1.8)); en.title = 'Llevar a la barra de abajo';
  en.onclick = function (e) { e.stopPropagation(); L(a).mini = true; pintarPanel(); pintarTop(); }; hd.appendChild(en); h.appendChild(hd);
  var pista = el('div', 'pista3'), f1 = el('i'); pista.appendChild(f1); h.appendChild(pista);
  var ol = el('ol', 'pasos3'); h.appendChild(ol);
  var pq = el('div', 'pq10'), pqi = el('div'), esp = el('button', 'esp10'); esp.appendChild(el('span', null, 'Esperando tu respuesta abajo'));
  esp.appendChild(svgTexto('<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v10M4 9l4 4 4-4"/></svg>'));
  esp.onclick = function (e) { e.stopPropagation(); verPregunta(a); }; pqi.appendChild(esp); pq.appendChild(pqi); w.appendChild(pq);
  w.appendChild(lb6('Lo que va haciendo')); var fd = el('div', 'feed6'); w.appendChild(fd);
  w.appendChild(lb6('Resultado'));
  var rs = el('div', 'res8'), mini = el('div', 'mini8'), bar = el('div', 'bar8'); bar.appendChild(el('i')); mini.appendChild(bar);
  var pg = el('div', 'pg8'); ['tl', 'st', 'im'].forEach(function (k) { pg.appendChild(el('i', k)); }); var tx = el('span', 'tx'); for (var i = 0; i < 4; i++) tx.appendChild(el('i')); pg.appendChild(tx); mini.appendChild(pg); rs.appendChild(mini);
  var ro = el('div', 'ro8'), rt = el('div', 'tt6'), rb = el('b'), rst = el('small'); rt.appendChild(rb); rt.appendChild(rst); ro.appendChild(rt);
  var ra = el('button', 'bt8p', 'Abrir'); ra.onclick = function (e) { e.stopPropagation(); if (ra._ruta) abrirLocal(a, ra._ruta, 'abrir'); }; ro.appendChild(ra); rs.appendChild(ro); w.appendChild(rs);
  var qh = el('button', 'qh6'); qh.appendChild(el('span', null, 'Qué hace esta skill')); var fq = el('span', 'fl'); fq.appendChild(icono('chev')); qh.appendChild(fq); w.appendChild(qh);
  var qb = el('div', 'qb6'), qi = el('div'); qi.appendChild(el('p', null, info.descripcion || 'Sin descripción.'));
  var mt = el('div', 'meta3'); mt.appendChild(el('span', null, nombreTema(info.categoria))); mt.appendChild(el('span', null, 'Con ' + motorN(motorChat(a)))); qi.appendChild(mt); qb.appendChild(qi); w.appendChild(qb);
  qh.onclick = function (e) { e.stopPropagation(); qh.classList.toggle('on'); qb.classList.toggle('on'); };
  var pie = el('div', 'pie5 suelto'); w.appendChild(pie);
  var lis = [], pasosF = '';
  function pasos(run, pide, vivo, pausa) {
    var ps = run.pasos && run.pasos.length ? run.pasos : [{ texto: run._arr || run.estado === 'arrancando' ? 'Armando el plan' : 'Leyendo lo que le pediste', estado: 'now' }];
    var f = JSON.stringify(ps.map(function (p) { return p.texto; }));
    if (f !== pasosF) {
      pasosF = f; ol.textContent = ''; lis = [];
      ps.forEach(function (p) { var li = el('li'), t2 = el('div', 'tx'); li.appendChild(el('i', 'mk')); t2.appendChild(el('div', null, p.texto)); t2.appendChild(el('div', 'vv')); li.appendChild(t2); ol.appendChild(li); lis.push(li); });
    }
    var fin = run.estado === 'listo', np = pausa ? ((run.pausa || {}).paso || 0) : 0;
    lis.forEach(function (li, i) {
      var p = ps[i], e = fin || p.estado === 'done' ? 'hecho' : pausa ? (i + 1 === np ? 'pausa' : 'luego') : p.estado === 'now' ? (pide ? 'pide' : 'ahora') : 'luego', vv = li.querySelector('.vv');
      if (li.dataset.e !== e) {
        var era = li.dataset.e; li.dataset.e = e; li.className = e; li.firstChild.textContent = '';
        if (e === 'hecho') li.firstChild.appendChild(ico3('check', 12, 2.4));
        if (era && e === 'hecho') animar(li.firstChild, curvaGel(260, 12, -18, 480), function (g) { return { transform: 'scale(' + (1 - g * .2).toFixed(3) + ')' }; }, { ms: 480 });
      }
      if (e === 'pide') ponTexto(vv, 'Necesita tu respuesta');
      else if (e === 'pausa') ponTexto(vv, 'Se detuvo aquí');
      else if (e === 'ahora') ponTexto(vv, vivo);
      else vv.textContent = '';
    });
  }
  var upd = function () {
    var run = corrida(a); if (!run) return;
    PROC.id = run.id;
    var fin = run.estado === 'listo', pausa = run.estado === 'pausada', pide = !pausa && !!preguntaDe(a), F = feedDe(a, run), hace = hechoEnSimple(fotoDe(a).hace);
    h.classList.toggle('fin', fin); f1.style.width = Math.max(2, progreso(run) * 100) + '%';
    pasos(run, pide, hace || (run._arr ? 'Lo está preparando…' : ''), pausa);
    pq.classList.toggle('on', pide);
    fd.textContent = '';
    F.xs.slice(0, cuatro()).forEach(function (x, i) {
      var tu = x.txt.indexOf('Tu respuesta: ') === 0, d = el('div', (i === 0 ? 'uno' : '') + (x.nuevo && i === 0 ? ' nuevo' : '') + (tu ? ' tu' : '')), sp = el('span');
      d.appendChild(el('i'));
      if (tu) { sp.appendChild(el('b', null, 'Tu respuesta:')); sp.appendChild(document.createTextNode(x.txt.slice(14))); } else sp.textContent = x.txt;
      d.appendChild(sp); d.appendChild(el('small', null, haceTxt(x.t))); fd.appendChild(d);
    });
    F.xs.forEach(function (x) { x.nuevo = false; });
    var ruta = ultimoArchivo(F), era = rs.classList.contains('on');
    rs.classList.toggle('on', fin); rb.textContent = ruta ? ruta.split(/[\\/]/).pop() : 'Lo que te deja';
    ponTexto(rst, fin ? (run.resumen ? String(run.resumen).split('\n')[0].slice(0, 90) : 'Listo') : pausa ? textoPausa(run) : 'Se está armando…');
    ra._ruta = ruta; ra.style.display = fin && ruta ? '' : 'none';
    if (fin && !era && ruta && MOV) ra.animate([{ opacity: 0, transform: 'scale(.9)' }, { opacity: 1, transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.34,1.56,.64,1)' });
    var modo = fin ? 'fin' : pausa ? 'pausa' : 'corre';
    if (pie._modo !== modo) {
      var habia = !!pie._modo; pie._modo = modo; pie.textContent = '';
      if (pausa) {
        var pz6 = el('span', 'pausa6'); pz6.appendChild(el('span', null, textoPausa(run))); pie.appendChild(pz6);
        var sg = el('button', 'bt5 ac', 'Seguir'); sg.onclick = function (e) { e.stopPropagation(); seguirSkill(a, corrida(a) || run); }; pie.appendChild(sg);
        var cp = el('button', 'bt5', 'Cerrar'); cp.onclick = function (e) { e.stopPropagation(); cerrarProceso(a); }; pie.appendChild(cp);
      } else if (fin) { var hc = el('span', 'hecho6'); hc.appendChild(ico3('check', 13, 2.4)); hc.appendChild(el('span', null, 'Terminó')); pie.appendChild(hc); var ce = el('button', 'bt5', 'Cerrar'); ce.onclick = function (e) { e.stopPropagation(); cerrarProceso(a); }; pie.appendChild(ce); }
      else { var de = el('button', 'bt5', 'Detener'); de.onclick = function (e) { e.stopPropagation(); detenerProceso(a); }; pie.appendChild(de); }
      if (habia && MOV) pie.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, easing: 'ease-out' });
    }
  };
  PROC = { ag: a.id, k: r.skill, id: r.id, w: w, h: h, upd: upd, prev: null };
  upd(); eventosProceso(a);
}
function lb6(t) { var l = el('div', 'lb6'); l.appendChild(el('span', null, t)); return l; }
function actualizarProceso(a) { if (PROC && a && PROC.ag === a.id && PROC.w.isConnected) { PROC.upd(); eventosProceso(a); } }

/* ---- la barra sobre la caja: la misma tarjeta, encogida ---- */
function construirBarra(a, r) {
  var b = el('div', 'pa3'); b.title = 'Ver el proceso completo'; b._nuevo = true;
  b.appendChild(el('b', 'nm5', nombreSkill(r.skill)));
  var vt = el('span', 'v5'); b.appendChild(vt);
  var mini = el('span', 'mini5'), mf = el('i'); mini.appendChild(mf); b.appendChild(mini);
  var acts = el('span', 'acts3'); b.appendChild(acts);
  b.onclick = function (e) { if (e.target.closest('button')) return; verProceso(a); };
  BARRA = { ag: a.id, k: r.skill, b: b, vt: vt, mf: mf, acts: acts, modo: '' };
  return b;
}
function actualizarBarra(a) {
  if (!BARRA || !a || BARRA.ag !== a.id || !BARRA.b.isConnected) return;
  var r = corrida(a); if (!r) return;
  var fin = r.estado === 'listo', pausa = r.estado === 'pausada', pide = !pausa && !!preguntaDe(a), F = feedDe(a, r);
  BARRA.b.classList.toggle('fin', fin); BARRA.b.classList.toggle('pide', pide); BARRA.b.classList.toggle('pausa', pausa);
  BARRA.mf.style.width = Math.max(2, progreso(r) * 100) + '%';
  var ahora = (r.pasos || []).filter(function (p) { return p.estado === 'now'; })[0];
  ponTexto(BARRA.vt, fin ? 'Terminó' + (ultimoArchivo(F) ? ' · ' + ultimoArchivo(F).split(/[\\/]/).pop() : '') : pausa ? textoPausa(r) : pide ? a.n + ' te pregunta algo' : hechoEnSimple(fotoDe(a).hace) || (ahora && ahora.texto) || 'Armando el plan…');
  var modo = fin ? 'fin' : pausa ? 'pausa' : 'corre';
  if (BARRA.modo !== modo) {
    var antes = BARRA.modo; BARRA.modo = modo; BARRA.acts.textContent = '';
    var bt = function (cls, t, fn) { var x = el('button', 'bt5' + (cls ? ' ' + cls : ''), t); x.onclick = function (e) { e.stopPropagation(); fn(); }; BARRA.acts.appendChild(x); };
    if (fin) { var ru = ultimoArchivo(F); if (ru) bt('ac', 'Abrir', function () { abrirLocal(a, ru, 'abrir'); }); bt('', 'Cerrar', function () { cerrarProceso(a); }); }
    else if (pausa) { bt('ac', 'Seguir', function () { seguirSkill(a, corrida(a) || r); }); bt('', 'Cerrar', function () { cerrarProceso(a); }); }
    else { bt('', 'Ver proceso', function () { verProceso(a); }); bt('', 'Detener', function () { detenerProceso(a); }); }
    if (MOV && BARRA.b._visto && (modo === 'fin' || antes === 'fin')) BARRA.acts.animate([{ opacity: 0, transform: 'translateY(3px)' }, { opacity: 1, transform: 'none' }], { duration: 240, easing: 'cubic-bezier(.22,1,.36,1)' });
    BARRA.b._visto = true;
  }
}
function alturaActiva(h0, h1) {
  var A = $('#activa'); if (A._an) A._an.cancel();
  if (MOV) A._an = A.animate([{ height: h0 + 'px' }, { height: h1 + 'px' }], { duration: 460, easing: 'cubic-bezier(.22,1,.36,1)' });
  pegarAbajo(500);
}
function pintarBarra(a, on, vuela) {
  var A = $('#activa'), b = A.querySelector('.pa3:not(.sale)'), r = a && corrida(a);
  if (b && (!on || !BARRA || !r || BARRA.ag !== a.id || BARRA.k !== r.skill)) {
    var h0 = A.offsetHeight;
    if (vuela || b.style.visibility === 'hidden' || !MOV) { b.remove(); alturaActiva(h0, 0); }
    else {
      var vb = b; vb.classList.add('sale'); vb.style.pointerEvents = 'none';
      vb.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(12px) scale(.97,.75)' }], { duration: 260, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' }).onfinish = function () { vb.remove(); alturaActiva(h0, A.offsetHeight); };
    }
    BARRA = null; b = null;
  }
  if (on && !b) { b = construirBarra(a, r); A.appendChild(b); alturaActiva(0, A.offsetHeight); }
  if (on) actualizarBarra(a);
}
/* sobre la caja: la barra del proceso (cuando vive abajo) */
function pintarActiva() {
  var a = activo(); if (!a) return;
  var lugar = lugarProceso(a);
  if (lugar !== LUGAR || (lugar === 'panel' && !(PROC && PROC.ag === a.id && PROC.w.isConnected))) { pintarPanel(); return; }
  if (lugar === 'panel') actualizarProceso(a);
  else if (lugar === 'barra') { pintarBarra(a, true, false); eventosProceso(a); }
}

/* ---- en el chat, como en el prototipo: la marca «Empezó…» donde empezó la skill (y ahí se queda) y, al terminar, la
   tarjeta «Terminó» en su lugar por la hora de fin (50_chat.js · pintarHilo): abajo de tu respuesta, no arriba ---- */
function modoMarca(e, viva) { return viva || e.estado === 'listo' ? 'empezo' : e.estado === 'pausada' && (e.pausa || {}).motivo !== 'detenida' ? 'pausa' : 'alto'; }
function marcaSkill(a, e, viva) {
  var nom = nombreSkill(e.skill), modo = modoMarca(e, viva), alto = modo !== 'empezo';
  var mk = el('button', 'marca3' + (alto ? ' alto' : '')), sl = el('span', 'mslot');
  if (!alto) sl.appendChild(monitoDe('marca-' + e.id, a, 22)); else sl.appendChild(ico3('alto', 13, 2));
  mk.appendChild(sl); var tt = el('span'); tt.appendChild(document.createTextNode((modo === 'pausa' ? 'Se detuvo' : alto ? 'Detuviste' : 'Empezó') + ' ')); tt.appendChild(el('b', null, '«' + nom + '»')); mk.appendChild(tt);
  /* la marca no se rehace al terminar (no repite su entrada): si corre todavía se ve al momento de usarla */
  function corre() { var v = ejecVigente(a) || corrida(a); return !!(v && v.id === e.id); }
  mk.title = viva ? 'Ver su proceso' : '';
  mk.onpointerenter = function () { mk.title = corre() ? 'Ver su proceso' : ''; };
  mk.onclick = function (ev) { ev.stopPropagation(); if (corre()) verProceso(a); var mm = monoObj('marca-' + e.id, a); if (mm) { mm.salta(.9); feliz(mm, 600); } };
  return mk;
}
function archivoFin(e) { return FEED[e.id] ? ultimoArchivo(FEED[e.id]) : ''; }
function finSkill(a, e) {
  var nom = nombreSkill(e.skill), w = el('div', 'fin3'), ms = el('span', 'mslot'), key = 'fin3|' + e.id, m = MONOS[key + '|' + a.id];
  if (!m) { m = MONOS[key + '|' + a.id] = new Monito(a.c, a.f, 60); m.setEstado('termino'); } else if (TODOS.indexOf(m) < 0) TODOS.push(m);
  ms.appendChild(m.el); w.appendChild(ms);
  var t = el('div', 'tt'); t.appendChild(el('b', null, 'Terminó «' + nom + '»'));
  var res = el('div', 'res3'); res.appendChild(ico3('doc', 14, 1.8)); res.appendChild(el('span', null, e.resumen ? String(e.resumen).split('\n')[0].slice(0, 120) : (e.pasos || []).length + ' pasos'));
  var ruta = archivoFin(e);
  if (ruta) { var ab = el('button', 'bt5 ac', 'Abrir'); ab.onclick = function (ev) { ev.stopPropagation(); abrirLocal(a, ruta, 'abrir'); }; res.appendChild(ab); }
  t.appendChild(res); w.appendChild(t);
  return w;
}

/* ---- el monito del agente acompaña el proceso: camina por la orilla de arriba de la tarjeta (o de la barra) ---- */
var ANIMA = MOV;
var ACTOR = { h: null, m: null, firma: '', x: null, y: null, fx: .24, dur: .8, vel: 110, recalc: false, ocul: 0, oculMeta: 0, base: 0, hide0: 0, esc: .82, ult: 0, pie: 0, parp: 0, mx: 0, my: 2, t: [], agarra: false, ag: '' };
function feliz(m, ms) { if (!m) return; m.modoOjo = 'feliz'; setTimeout(function () { if (m.modoOjo === 'feliz' && m.estado !== 'termino') m.modoOjo = 'normal'; }, ms || 700); }
function decoDe() { var D = $('#deco'); if (!D) { D = el('div'); D.id = 'deco'; document.body.appendChild(D); requestAnimationFrame(decoTic); } return D; }
function actorPrep(a) {
  if (!ANIMA || !a) return; var firma0 = a.id + a.c + a.f;
  if (ACTOR.firma === firma0 && ACTOR.m) return;
  var D = decoDe(); D.textContent = ''; if (ACTOR.m) { var k = TODOS.indexOf(ACTOR.m); if (k >= 0) TODOS.splice(k, 1); }
  ACTOR.firma = firma0; ACTOR.ag = a.id; ACTOR.x = null;
  ACTOR.h = el('div', 'actor'); var m = ACTOR.m = new Monito(a.c, a.f, 60); m.quieto = true; m.setEstado('libre');
  ACTOR.h.appendChild(m.el); D.appendChild(ACTOR.h);
  var esc = 60 / 118; ACTOR.base = (m.G.base + 24) * esc; ACTOR.hide0 = Math.max(6, (m.G.base - m.oy - 18) * esc);
  m.el.style.transformOrigin = '30px ' + ACTOR.base.toFixed(1) + 'px';
}
function plan(ms, fn) { ACTOR.t.push(setTimeout(function () { if (ACTOR.m && ANIMA) fn(ACTOR.m); }, ms)); }
function limpiarPlan() { ACTOR.t.forEach(clearTimeout); ACTOR.t = []; }
function irA(fx, seg) { ACTOR.fx = Math.max(0, Math.min(1, fx)); ACTOR.dur = seg || .8; ACTOR.recalc = true; }
function mirar(x, y) { ACTOR.mx = x; ACTOR.my = y; }
function brincaMonito() { var m = ACTOR.m; if (m && ANIMA && LUGAR) { m.salta(.7); feliz(m, 700); } }
function lee(inicio) {
  var m = ACTOR.m, b = 0;
  m.modoOjo = 'normal'; m.tabre = 1;
  if (inicio) {
    if (ACTOR.x == null) { ACTOR.fx = .24; ACTOR.oculMeta = 1; ACTOR.ocul = 1; }
    else { irA(.24, .6); plan(560, function () { ACTOR.oculMeta = 1; }); b = 600; }
    plan(b + 140, function () { mirar(-4, -.5); });
    plan(b + 460, function () { mirar(4, -.5); });
    plan(b + 780, function (m) { mirar(0, 1); m.salta(.75); ACTOR.oculMeta = 0; });
    b += 1040;
  }
  plan(b, function () { mirar(-2.4, 3); });
  plan(b + 300, function () { mirar(2.4, 3); });
  plan(b + 520, function (m) { m.signo('pregunta', { donde: 'der', esc: .62, sube: 8, dur: 1100 }); });
  plan(b + 620, function () { mirar(-2.4, 3); });
  plan(b + 920, function () { mirar(2.4, 3); });
  plan(b + 1220, function (m) { mirar(0, -2); m.tabre = 1.1; m.salta(.4); m.signo('idea', { donde: 'arriba', esc: .62, sube: 6, dur: 1200 }); });
  plan(b + 1620, function (m) { m.tabre = 1; mirar(0, 2); });
}
function trabaja() {
  irA(.5, .55);
  plan(600, function (m) { mirar(0, 3); m.modoOjo = 'apretado'; m.salta(.3); m.gel.vel += 28; });
  plan(900, function (m) { m.salta(.3); m.gel.vel -= 28; m.signo('lineas', { donde: 'arriba', esc: .58, sube: 5, dur: 850 }); });
  plan(1200, function (m) { m.salta(.32); m.gel.vel += 28; });
  plan(1500, function (m) { m.modoOjo = 'normal'; mirar(0, 2); });
}
function revisa() {
  irA(.04, .55);
  plan(560, function () { mirar(-5, 4.2); });
  plan(860, function () { irA(.96, .62); });
  plan(1500, function () { mirar(5, 4.2); });
  plan(1760, function (m) { mirar(0, 0); m.salta(.4); m.signo('check', { donde: 'arriba', color: '#3fbf7f', esc: .6, sube: 5, dur: 1000 }); });
}
function entrega() {
  irA(.7, .55);
  plan(600, function () { mirar(0, -1.5); });
  plan(660, function (m) { m.salta(.85); feliz(m, 800); m.rafaga(4); });
}
/* su actividad por paso: lee, trabaja, revisa y entrega (los pasos de en medio trabajan) */
function guion(i, n, reaccion) {
  limpiarPlan(); var m = ACTOR.m; if (!m || !ANIMA) return;
  var t0 = 0;
  if (reaccion) { t0 = 560; m.modoOjo = 'normal'; m.salta(.7); feliz(m, 520); m.signo('chispa', { donde: 'der', esc: .62, sube: 12 }); }
  var k = i <= 0 ? 0 : i >= n - 1 ? 3 : i === n - 2 && n > 3 ? 2 : 1;
  var hace = [function () { lee(false); }, trabaja, revisa, entrega][k];
  if (t0) plan(t0, function () { hace(); }); else hace();
}
function festejo() {
  limpiarPlan(); var m = ACTOR.m; if (!m || !ANIMA) return;
  ACTOR.oculMeta = 0; mirar(0, -1); m.modoOjo = 'feliz'; m.salta(.85); m.rafaga(4);
  plan(520, function (m) { m.signo('palomita', { donde: 'der', color: '#3fbf7f', esc: .7, sube: 8, dur: 1300 }); });
  plan(2400, function (m) { m.salta(.5); });
}
function decoEvento(a, ev, r) {
  if (ev === 'fuera') { limpiarPlan(); ACTOR.x = null; return; }
  if (!ANIMA || !a) return;
  actorPrep(a); var m = ACTOR.m; if (!m) return;
  if (ev === 'inicio') { m.modoOjo = 'normal'; limpiarPlan(); lee(true); }
  else if (ev === 'paso') guion(r ? pasosHechos(r) : 1, r ? (r.pasos || []).length : 4, true);
  else if (ev === 'fin') festejo();
  else if (ev === 'pide') {
    /* se queda donde va, mira hacia la caja, da un brinco chico y saca «?» cada 2.5 s */
    limpiarPlan(); irA(ACTOR.fxAhora == null ? ACTOR.fx : ACTOR.fxAhora, .05); ACTOR.oculMeta = 0; m.modoOjo = 'normal';
    var mira = function () { if (LUGAR === 'panel') mirar(-4.5, 3.8); else mirar(0, 4.6); };
    mira(); m.tabre = 1.12; m.salta(.45);
    (function ciclo(t) { plan(t, function (m) { mira(); m.signo('pregunta', { donde: 'der', esc: .95, sube: 8, dur: 2300 }); if (Math.random() < .5) m.parpadea(); ciclo(2500); }); })(250);
  } else if (ev === 'respuesta') {
    limpiarPlan(); m.tabre = 1; mirar(0, -1.5); feliz(m, 900); m.salta(.8); m.signo('idea', { donde: 'arriba', esc: .72, sube: 6, dur: 1200 });
    plan(900, function () { var rr = corrida(a); guion(rr ? pasosHechos(rr) : 1, rr ? (rr.pasos || []).length : 4, false); });
  }
}
/* lo que cambió desde la última vez que se miró: un paso más, terminó, te preguntó o contestaste */
function eventosProceso(a) {
  var r = corrida(a), P = PROC && PROC.ag === a.id ? PROC : BARRA && BARRA.ag === a.id ? BARRA : null; if (!r || !P) return;
  var ahora = { id: r.id, h: pasosHechos(r), fin: r.estado === 'listo', pide: !!preguntaDe(a) }, antes = P.prev; P.prev = ahora;
  if (!antes) return;                      /* la primera vez solo se mira */
  if (ahora.fin && !antes.fin) return decoEvento(a, 'fin', r);
  if (ahora.pide && !antes.pide) return decoEvento(a, 'pide', r);
  if (!ahora.pide && antes.pide) return decoEvento(a, 'respuesta', r);
  if (ahora.h > antes.h) decoEvento(a, 'paso', r);
}
function anclaActor() {
  if (VUELO) return { el: VUELO.sh, esc: .82 };
  var e = anclaDe(LUGAR); return e ? { el: e, esc: .82 } : null;
}
function visibleEn(e, r) {
  if (!e.isConnected || r.width < 30) return false;
  if (getComputedStyle(e).visibility === 'hidden' && !(VUELO && VUELO.sh === e)) return false;
  var Sb = $('#side').getBoundingClientRect(); if (e.closest('#side') && (r.top < Sb.top + 4 || r.bottom > Sb.bottom)) return false;
  return true;
}
var DECO_T = performance.now();
function decoTic(ahora) {
  requestAnimationFrame(decoTic);
  var dt = Math.min(.04, (ahora - DECO_T) / 1000); DECO_T = ahora;
  if (!ACTOR.h) return;
  var a = activo(), A = anclaActor(), anc = A && A.el, r = anc ? anc.getBoundingClientRect() : null;
  var ok = !!(ANIMA && a && ACTOR.ag === a.id && LUGAR && anc && visibleEn(anc, r));
  ACTOR.h.style.opacity = ok ? 1 : 0;
  if (!ok) { ACTOR.x = null; return; }
  var m = ACTOR.m, D = $('#deco').getBoundingClientRect(), tx, ty;
  /* viaja junto con su ancla (la barra sube cuando crece la caja): nunca queda encima del texto */
  if (ACTOR.ranc === anc && ACTOR.ry != null && ACTOR.x != null && !VUELO) { var mov = r.top - ACTOR.ry; if (Math.abs(mov) > .05 && Math.abs(mov) < 90) ACTOR.y += mov; }
  ACTOR.ranc = anc; ACTOR.ry = r.top;
  var mg = 26, w = Math.max(10, r.width - 2 * mg); tx = r.left + mg + w * ACTOR.fx; ty = r.top + 1;
  if (ACTOR.x != null) ACTOR.fxAhora = Math.max(0, Math.min(1, (ACTOR.x - r.left - mg) / w));
  if (ACTOR.x == null) { ACTOR.x = tx; ACTOR.y = ty; ACTOR.esc = A.esc; }
  ACTOR.esc = hacia(ACTOR.esc, A.esc, 7, dt);
  var dx = tx - ACTOR.x;
  if (ACTOR.recalc) { ACTOR.vel = Math.max(60, Math.abs(dx) / ACTOR.dur); ACTOR.recalc = false; }
  if (VUELO) { ACTOR.x = hacia(ACTOR.x, tx, 30, dt); ACTOR.y = ty; }
  else { ACTOR.x += Math.sign(dx) * Math.min(ACTOR.vel, Math.abs(dx) * 7) * dt; ACTOR.y = hacia(ACTOR.y, ty, 18, dt); }
  ACTOR.ocul = hacia(ACTOR.ocul, ACTOR.oculMeta, 10, dt);
  if (VUELO && m.modoOjo === 'normal') { m.modoOjo = 'apretado'; ACTOR.agarra = true; }
  if (!VUELO && ACTOR.agarra) { ACTOR.agarra = false; if (m.modoOjo === 'apretado') m.modoOjo = 'normal'; }
  if (!VUELO && Math.abs(dx) > 2.5) {
    if (ahora - ACTOR.ult > 270) { ACTOR.ult = ahora; m.salta(.34); ACTOR.pie ^= 1; m.gel.vel += (ACTOR.pie ? 1 : -1) * 18; }
    m.tgx = dx > 0 ? 5 : -5; m.tgy = -.5;
  } else { m.tgx = ACTOR.mx; m.tgy = ACTOR.my; }
  if (ahora > ACTOR.parp) { ACTOR.parp = ahora + 2600 + Math.random() * 2400; if (m.modoOjo === 'normal') m.parpadea(Math.random() < .25); }
  ACTOR.h.style.transform = 'translate(' + (ACTOR.x - 90).toFixed(1) + 'px,' + (ACTOR.y - D.top - 140).toFixed(1) + 'px)';
  m.el.style.transform = 'scale(' + ACTOR.esc.toFixed(3) + ')';
  m.el.style.top = (140 - ACTOR.base + ACTOR.ocul * ACTOR.hide0 * ACTOR.esc).toFixed(1) + 'px';
}

/* ---------- skills v11 · el panel «Primero el tema» ----------
   Favoritas arriba, luego una tarjeta por tema (su objeto C-1, cuántas tiene y las primeras) y el buscador. Dentro de un
   tema, sus skills; una fila se abre en su lugar (qué hace, sus pasos, cuándo la usaste) y «Usar» la lanza: la fila vuela
   a la tarjeta del proceso. Las skills y su tema salen del índice del cerebro (skills/<tema>/<skill>/SKILL.md). */
/* un SVG escrito como texto → su nodo (con DOMParser: la página no asigna HTML como texto). Nunca truena: si no se puede
   armar, un punto por defecto. Ojo: 75_config.js tiene su propio svgDe (de piezas); este se llama distinto a propósito */
function svgTexto(s) {
  try {
    var d = _PARSER.parseFromString(String(s).replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" '), 'image/svg+xml'), r = d && d.documentElement;
    if (r && String(r.nodeName).toLowerCase() === 'svg' && !(r.getElementsByTagName && r.getElementsByTagName('parsererror').length)) return document.importNode(r, true);
  } catch (e) { /* cae al de por defecto */ }
  return svgPorDefecto();
}
function svgPorDefecto() {
  var ns = 'http://www.w3.org/2000/svg', s = document.createElementNS(ns, 'svg'), c = document.createElementNS(ns, 'circle');
  s.setAttribute('width', '12'); s.setAttribute('height', '12'); s.setAttribute('viewBox', '0 0 24 24');
  c.setAttribute('cx', '12'); c.setAttribute('cy', '12'); c.setAttribute('r', '4'); c.setAttribute('fill', 'currentColor'); s.appendChild(c);
  return s;
}
var I3 = {
  lupa: '<circle cx="11" cy="11" r="6.5"/><path d="m20.5 20.5-4.8-4.8"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  estrella: '<path d="m12 3.2 2.7 5.5 6 .9-4.35 4.25 1.03 6L12 17l-5.38 2.85 1.03-6L3.3 9.6l6-.9z"/>',
  chispa: '<path d="M11 3.5 12.8 8.2 17.5 10l-4.7 1.8L11 16.5l-1.8-4.7L4.5 10l4.7-1.8z"/><path d="m18.5 15.5.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8z"/>',
  check: '<path d="M5 12.5 9.5 17 19 7.5"/>',
  abajo: '<path d="M7 8.5l5 5 5-5"/><path d="M5 19h14"/>',
  doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  alto: '<rect x="6.5" y="6.5" width="11" height="11" rx="2.5"/>'
};
function ico3(k, px, sw) { if (!I3[k]) return svgPorDefecto(); return svgTexto('<svg width="' + px + '" height="' + px + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + (sw || 1.7) + '" stroke-linecap="round" stroke-linejoin="round">' + I3[k] + '</svg>'); }
function chev6(atras) { return svgTexto('<svg class="' + (atras ? '' : 'chev6') + '" width="' + (atras ? 16 : 14) + '" height="' + (atras ? 16 : 14) + '" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="' + (atras ? 'M10 3.5 5.5 8l4.5 4.5' : 'M6 3.5 10.5 8 6 12.5') + '"/></svg>'); }
/* los objetos de tema (C-1): objetos y símbolos, nunca personajes. o1 es el principal; o2 y s2, el detalle */
var EMB = {
  contenido: '<path class="o1" d="M10 4.5h9.2l6.3 6.3V25.5a2.5 2.5 0 0 1-2.5 2.5H10a2.5 2.5 0 0 1-2.5-2.5V7A2.5 2.5 0 0 1 10 4.5z"/><path class="o2" d="M19.2 4.5v4.8a1.5 1.5 0 0 0 1.5 1.5h4.8z"/><rect class="o2" x="11" y="15" width="11" height="2.6" rx="1.3"/><rect class="o2" x="11" y="20.2" width="7.5" height="2.6" rx="1.3"/>',
  investigacion: '<path class="s2" d="M20 20 26 26" fill="none" stroke-width="5" stroke-linecap="round"/><circle class="o1" cx="14" cy="14" r="9"/><path d="M9.6 12.2a5 5 0 0 1 4.4-3.6" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="2.2" stroke-linecap="round"/>',
  consultoria: '<path class="s2" d="M12.4 9.5V8a2.4 2.4 0 0 1 2.4-2.4h2.4A2.4 2.4 0 0 1 19.6 8v1.5" fill="none" stroke-width="2.8"/><rect class="o1" x="5" y="9.5" width="22" height="17.5" rx="4"/><rect class="o2" x="5" y="15.6" width="22" height="2.6"/><rect class="o2" x="14" y="13.8" width="4" height="6" rx="1.5"/>',
  infraestructura: '<rect class="o1" x="5" y="20" width="22" height="7.5" rx="3"/><rect class="o2" x="8" y="12.2" width="16" height="7" rx="2.8"/><rect class="o1" x="11" y="4.5" width="10" height="6.6" rx="2.5"/>',
  meta: '<path class="o1" d="M14.5 4.5c1 5.8 3.2 8 9 9-5.8 1-8 3.2-9 9-1-5.8-3.2-8-9-9 5.8-1 8-3.2 9-9z" stroke-width="2.4" stroke-linejoin="round" style="stroke:currentColor"/><path class="o2" d="M24 20.5c.45 2.3 1.25 3.1 3.5 3.5-2.25.45-3.05 1.25-3.5 3.5-.45-2.25-1.25-3.05-3.5-3.5 2.25-.4 3.05-1.2 3.5-3.5z"/>',
  /* un tema que no es de los cinco: cuatro cuadros, el mismo trato */
  otro: '<rect class="o1" x="5" y="5" width="9.5" height="9.5" rx="2.6"/><rect class="o2" x="17.5" y="5" width="9.5" height="9.5" rx="2.6"/><rect class="o2" x="5" y="17.5" width="9.5" height="9.5" rx="2.6"/><rect class="o1" x="17.5" y="17.5" width="9.5" height="9.5" rx="2.6"/>'
};
/* el objeto de cada tema por su nombre (la carpeta de skills/); lo que no se reconoce lleva el neutro */
var TEMA_OBJ = [
  ['contenido', /conten|escrit|redac|marketing|dise|copy|comunic|ense|social|video|imagen|blog/],
  ['investigacion', /investig|research|anali|review|revis|debug|test|datos|data|estudi/],
  ['consultoria', /consult|negoci|estrateg|venta|finanz|client|gesti|legal|proyecto|operac/],
  ['infraestructura', /infra|devops|constru|segur|deploy|servid|codigo|desarrollo|web|shopify|automat|herramient/],
  ['meta', /^meta|sistema|agente|memoria|skill/]
];
function objetoDe(tema) {
  var t = String(tema || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  for (var i = 0; i < TEMA_OBJ.length; i++) if (TEMA_OBJ[i][1].test(t)) return TEMA_OBJ[i][0];
  return 'otro';
}
function emblema(tema, px) {
  var s = el('span', 'emb7'); s.style.width = s.style.height = px + 'px';
  s.appendChild(svgTexto('<svg viewBox="0 0 32 32" width="' + px + '" height="' + px + '">' + EMB[objetoDe(tema)] + '</svg>'));
  return s;
}
function nombreTema(c) { c = temaDe(c); return c ? nombreSkill(c) : 'Otras'; }
/* el tema tal como viene del índice: su carpeta. Sin carpeta (la skill vive suelta en skills/), vacío o algo que no es
   texto → '' («Otras», con el objeto neutro); una carpeta nueva es su propio tema, con su nombre y sus acentos */
function temaDe(c) { return typeof c === 'string' ? c.trim() : ''; }
/* lo del índice, como lo pinta el panel: nombre en palabras normales, una línea corta, la larga, sus pasos y su tema */
function skillsVista(a) {
  return skillsDe(a).filter(function (s) { return s && s.nombre; }).map(function (s) {
    var d = String(s.descripcion || ''), corta = (d.match(/^[^.!?\n]{1,140}[.!?]?/) || [''])[0].replace(/[.]$/, '');
    return { k: String(s.nombre), n: nombreSkill(s.nombre), c: temaDe(s.categoria), d: corta || 'Sin descripción', larga: d,
      pasos: Array.isArray(s.pasos) ? s.pasos.map(String) : [],
      u: usoSkill(a, s.nombre), fij: (a.fijas || []).indexOf(s.nombre) >= 0 };
  });
}
function temasDe(vis) {
  var por = {};
  vis.forEach(function (s) { (por[s.c] = por[s.c] || []).push(s); });
  function peso(c) { return !c ? 2 : objetoDe(c) === 'meta' ? 1 : 0; }      // lo del sistema y «Otras», al final
  return Object.keys(por).sort(function (x, y) {
    return peso(x) - peso(y) || nombreTema(x).localeCompare(nombreTema(y), 'es');
  }).map(function (c) { return { c: c, n: nombreTema(c), xs: por[c] }; });
}
var SKP = { nivel: null, abierta: '', nav: false };     // nivel: el tema abierto ('' es «Otras»); null, ninguno
var FIRMA_SK = '';
function refrescarSkillsPanel() {
  var a = activo(); if (!a || S.PANEL !== 'skills') return;
  var f = firma(JSON.stringify(skillsVista(a)));
  if (f !== FIRMA_SK && !SKP.nav) { FIRMA_SK = f; var I = $('#sideIn'), L = I && I.querySelector('.lista3'); if (L && L._lista) L._lista(false); }
}
function usoSkill(a, nombre) {
  var e = (S.ejec[a.id] || []).filter(function (x) { return x.skill === nombre; })[0];
  return e ? cuando(Date.parse(e.actualizado || e.creado)) : '';
}
function panelSkills(I) {
  var a = activo(); if (!a) return;
  var w = el('div', 'sk3'); I.appendChild(w);
  var hd = el('div', 'hd3'); hd.appendChild(el('b', null, 'Skills'));
  var x = el('button', 'cb'); x.appendChild(icono('x')); x.title = 'Cerrar'; x.onclick = function (e) { e.stopPropagation(); abrirPanel(''); };
  hd.appendChild(x); w.appendChild(hd);
  var bus = el('label', 'bus3'); bus.appendChild(ico3('lupa', 15, 1.8));
  var q = el('input', 'sq3'); q.placeholder = 'Buscar una skill…'; q.value = S.SKQ || ''; q.spellcheck = false; bus.appendChild(q);
  var kb = el('kbd', null, '/'); bus.appendChild(kb);
  var lim = el('button', 'lim'); lim.appendChild(ico3('x', 12, 2)); lim.title = 'Borrar la búsqueda'; bus.appendChild(lim); w.appendChild(bus);
  function marcarBus() { kb.style.display = S.SKQ ? 'none' : ''; lim.style.display = S.SKQ ? '' : 'none'; }
  lim.onclick = function (e) { e.preventDefault(); e.stopPropagation(); q.value = ''; S.SKQ = ''; marcarBus(); lista(true); q.focus(); };
  var L = el('div', 'lista3'); w.appendChild(L);
  function rotulo(t, cls) { var l = el('div', 'lab3' + (cls ? ' ' + cls : '')); l.appendChild(el('span', null, t)); return l; }
  /* apretar: el aplastón y lo iluminado se quedan; después de un respiro (120 ms), el cambio */
  function apretable(b, alSoltar) {
    b.onpointerdown = function () { b.classList.add('apretada'); };
    b.onpointerleave = b.onpointercancel = function () { if (!b._va) b.classList.remove('apretada'); };
    b.onclick = function (e) { e.stopPropagation(); if (SKP.nav || b._va) return; b._va = true; b.classList.add('apretada'); setTimeout(alSoltar, MOV ? 120 : 0); };
  }
  /* el cambio de lista: la vieja sale en una copia con la misma caja exacta mientras la nueva entra (sin cuadro vacío ni
     texto doble); un candado contra el doble clic */
  function navegar(dir, cambiar) {
    if (SKP.nav) return; SKP.nav = true;
    var g = el('div', 'lista3'), st = L.scrollTop;
    g.style.cssText = 'position:absolute;margin:0;box-sizing:border-box;left:' + L.offsetLeft + 'px;top:' + L.offsetTop + 'px;width:' + L.clientWidth + 'px;height:' + L.clientHeight + 'px;pointer-events:none;overflow:hidden;z-index:2';
    while (L.firstChild) g.appendChild(L.firstChild);
    w.appendChild(g); g.scrollTop = st;
    cambiar(); lista(false); L.scrollTop = 0;
    if (!MOV) { g.remove(); SKP.nav = false; return; }
    w.classList.add('mueve');
    g.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateX(' + (-dir * 14) + 'px)' }], { duration: 130, easing: 'cubic-bezier(.3,0,.7,1)', fill: 'forwards' }).onfinish = function () { g.remove(); };
    L.animate([{ opacity: 0, transform: 'translateX(' + (dir * 20) + 'px)' }, { opacity: 1, transform: 'none' }], { duration: 280, delay: 115, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'backwards' }).onfinish = function () { w.classList.remove('mueve'); SKP.nav = false; };
  }
  function fila(s, conMarca) {
    var f = el('div', 'f3s' + (SKP.abierta === s.k ? ' abierta' : '')); f.dataset.k = s.k;
    var b = el('div', 'fila'); b.setAttribute('role', 'button'); b.tabIndex = 0;
    var t = el('span', 't'), nb = el('b'); if (conMarca) nb.appendChild(emblema(s.c, 16)); nb.appendChild(el('span', null, s.n)); nb.title = nombreTema(s.c); t.appendChild(nb);
    var dd = el('span', null, s.d); dd.style.paddingLeft = conMarca ? '26px' : '0'; t.appendChild(dd); b.appendChild(t);
    var ac = el('span', 'acc3');
    var us = el('button', 'usar3', 'Usar'); us.title = 'Usar con ' + a.n; us.onclick = function (e) { e.stopPropagation(); lanzarSkill(a, s, f); };
    var st = el('button', 'est3' + (s.fij ? ' on' : '')); st.appendChild(ico3('estrella', 14, 1.8)); st.title = s.fij ? 'Quitar de favoritas' : 'Fijar en favoritas';
    st.onclick = function (e) {
      e.stopPropagation(); if (SKP.nav) return;
      fijar(a, s.k); s.fij = !s.fij; st.classList.toggle('on', s.fij); st.title = s.fij ? 'Quitar de favoritas' : 'Fijar en favoritas';
      st.classList.add('brinca'); setTimeout(function () { st.classList.remove('brinca'); }, 140);
      nota(s.fij ? '«' + s.n + '» quedó en favoritas' : '«' + s.n + '» salió de favoritas');
      /* solo en «Favoritas» la fila se va (se cierra suave y luego se rehace la lista); en un tema o en la búsqueda, se queda */
      if (!s.fij && SKP.nivel === null && !(S.SKQ || '').trim()) { SKP.nav = true; setTimeout(function () { cerrarFila(f, function () { SKP.nav = false; lista(false); }); }, 200); }
    };
    ac.appendChild(us); ac.appendChild(st); b.appendChild(ac);
    b.onclick = function () { SKP.abierta = SKP.abierta === s.k ? '' : s.k; L.querySelectorAll('.f3s').forEach(function (y) { y.classList.toggle('abierta', y.dataset.k === SKP.abierta); }); };
    b.onkeydown = function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); b.onclick(); } };
    var d = el('div', 'det3'), d1 = el('div'), d2 = el('div', 'dt3'); d.appendChild(d1); d1.appendChild(d2);
    d2.appendChild(el('p', null, s.larga || 'Sin descripción.'));
    if (s.pasos.length) { var ol = el('ol'); s.pasos.forEach(function (p) { ol.appendChild(el('li', null, p)); }); d2.appendChild(ol); }
    var mt = el('div', 'meta3'); mt.appendChild(el('span', null, nombreTema(s.c))); mt.appendChild(el('span', null, s.u ? 'La usaste ' + s.u : 'Todavía no la usas'));
    d2.appendChild(mt); f.appendChild(b); f.appendChild(d);
    return f;
  }
  function cerrarFila(f, fin) {
    if (!MOV) return fin();
    var h = f.offsetHeight; f.style.overflow = 'hidden'; f.style.pointerEvents = 'none';
    f.animate([{ opacity: 1, height: h + 'px' }, { opacity: 0, height: h + 'px', offset: .35 }, { opacity: 0, height: '0px' }], { duration: 380, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' }).onfinish = fin;
  }
  function temas(vis) {
    var ts = temasDe(vis);
    if (SKP.nivel !== null) {
      var T = ts.filter(function (x) { return x.c === SKP.nivel; })[0];
      if (!T) SKP.nivel = null;
      else {
        var cab = el('div', 'niv6'), at = el('button', 'atras'); at.appendChild(chev6(true)); at.title = 'Volver a los temas';
        apretable(at, function () { navegar(-1, function () { SKP.nivel = null; SKP.abierta = ''; }); }); cab.appendChild(at);
        var mc = el('span', 'mmc'); mc.appendChild(emblema(T.c, 20)); cab.appendChild(mc); cab.appendChild(el('b', null, T.n)); cab.appendChild(el('i', null, String(T.xs.length)));
        L.appendChild(cab);
        T.xs.filter(function (s) { return s.fij; }).concat(T.xs.filter(function (s) { return !s.fij; })).forEach(function (s) { L.appendChild(fila(s, false)); });
        return;
      }
    }
    var fav = vis.filter(function (s) { return s.fij; });
    if (fav.length) { L.appendChild(rotulo('Favoritas')); fav.forEach(function (s) { L.appendChild(fila(s, true)); }); }
    L.appendChild(rotulo('Temas', fav.length ? 'tm8' : ''));
    ts.forEach(function (T) {
      var b = el('button', 'tema6'), mc = el('span', 'mmc'); mc.appendChild(emblema(T.c, 26)); b.appendChild(mc);
      var tt = el('span', 'tt6'), nm = el('span', 'nm8'); nm.appendChild(el('b', null, T.n)); nm.appendChild(el('i', null, String(T.xs.length))); tt.appendChild(nm);
      tt.appendChild(el('small', null, T.xs.slice(0, 2).map(function (s) { return s.n; }).join(', ') + (T.xs.length > 2 ? '…' : ''))); b.appendChild(tt);
      b.appendChild(chev6(false));
      apretable(b, function () { navegar(1, function () { SKP.nivel = T.c; SKP.abierta = ''; }); });
      L.appendChild(b);
    });
  }
  function lista(anim) {
    L.textContent = '';
    var todas = skillsVista(a), qq = (S.SKQ || '').trim().toLowerCase();
    var vis = todas.filter(function (s) { return !qq || (s.n + ' ' + s.k + ' ' + s.larga + ' ' + nombreTema(s.c)).toLowerCase().indexOf(qq) >= 0; });
    if (!todas.length) { var v0 = el('div', 'vacio3'); v0.appendChild(el('b', null, a.n + ' todavía no tiene skills')); v0.appendChild(el('span', null, 'Enséñale una tarea en el chat y pídele que la guarde como skill.')); L.appendChild(v0); }
    else if (!vis.length) { var v = el('div', 'vacio3'); v.appendChild(el('b', null, 'Ninguna skill con «' + S.SKQ.trim() + '»')); v.appendChild(el('span', null, 'Prueba con otra palabra, o enséñale la tarea.')); L.appendChild(v); }
    else if (!qq) temas(vis);
    else { L.appendChild(rotulo(vis.length === 1 ? '1 resultado' : vis.length + ' resultados')); vis.forEach(function (s) { L.appendChild(fila(s, true)); }); }
    var nv = el('button', 'nueva'); nv.appendChild(ico3('chispa', 14, 1.8)); nv.appendChild(el('span', null, 'Enséñale una tarea nueva'));
    nv.onclick = function (e) { e.stopPropagation(); abrirPanel(''); var t = $('#ta'); t.value = 'Quiero enseñarte una tarea para que la guardes como skill: '; t.focus(); pintarSend(); };
    L.appendChild(nv);
    FIRMA_SK = firma(JSON.stringify(todas));
    if (anim && MOV) L.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease-out' });
  }
  L._lista = lista;
  q.oninput = function () { S.SKQ = q.value; marcarBus(); SKP.abierta = ''; lista(true); };
  q.onkeydown = function (e) { if (e.key === 'Escape' && S.SKQ) { e.stopPropagation(); q.value = ''; S.SKQ = ''; marcarBus(); lista(true); } };
  marcarBus(); lista(true);
}
function fijar(a, nombre) {
  var i = a.fijas.indexOf(nombre); if (i >= 0) a.fijas.splice(i, 1); else a.fijas.unshift(nombre);
  post('/api/front/prefs', { agente: a.id, fijas: a.fijas }).catch(function (e) {
    var k = a.fijas.indexOf(nombre); if (i >= 0) { if (k < 0) a.fijas.splice(i, 0, nombre); } else if (k >= 0) a.fijas.splice(k, 1);
    nota(e.message, true); if (S.PANEL === 'skills') pintarPanel();
  });
}
function cerrarHoja() { document.querySelectorAll('.velo7').forEach(function (v) { v.remove(); }); }
