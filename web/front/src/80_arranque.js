/* ================= crear un agente (AG8-b): la ventana «Nuevo agente», con su motor y «Ya tengo un agente» =================
   El mismo proceso que la tarjeta del hub: /api/front/crear llama a su job oficial y aquí se pintan sus pasos en vivo.
   El monito grande cambia en vivo con la cara y el color; el nombre se escribe como quieras y su comando sale solo
   («Brisa Azul» → brisa-azul). El motor se elige solo (el que ya tiene tu sesión) y se puede cambiar; uno sin sesión NO
   bloquea: el agente nace y despierta cuando entras a tu cuenta (Configuración → Motores). «Ya tengo un agente» conecta
   uno que ya existe: lo que encontré en esta computadora o la carpeta que pegas. Los textos llegan con su clave
   (/api/front/textos: los catálogos de agregar); sin ellos, el español de aquí. */
var TXA = null;
function tA(k, es, kw) {
  var s = (TXA && TXA[k]) || es;
  Object.keys(kw || {}).forEach(function (n) { s = s.split('{' + n + '}').join(kw[n]); });
  return s;
}
function comandoDe(t) {
  var s = String(t || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  s = s.replace(/[\s.]+/g, '-').replace(/[^a-z0-9_-]/g, '').replace(/-{2,}/g, '-').replace(/^[-_]+|[-_]+$/g, '');
  return s.slice(0, 32).replace(/[-_]+$/g, '');
}
function motorUsable(m) { return !!(m && m.listo && m.sesion !== false && m.estado !== 'sin_sesion'); }
function motorPorDefecto() {
  var usables = S.motores.filter(motorUsable), g = CFG_LOCAL.get('motorDef');
  return (usables.filter(function (m) { return m.id === g; })[0] || usables.filter(function (m) { return m.id === 'claude-code'; })[0] || usables[0] || {}).id || '';
}
function motorInicial() {
  var d = motorPorDefecto(); if (d) return d;
  var inst = S.motores.filter(function (m) { return m.instalado; });
  return (inst[0] || S.motores.filter(function (m) { return m.id === 'claude-code'; })[0] || S.motores[0] || { id: 'claude-code' }).id;
}
function estadoMotor(m) {
  if (!m) return ['', tA('agregar.motor.viendo', 'viendo…')];
  if (motorUsable(m)) return ['ok', tA('agregar.motor.listo', '✓ listo')];
  if (!m.instalado) return ['', tA('agregar.motor.no_instalado', 'no instalado')];
  if (m.estado === 'verificando') return ['', tA('agregar.motor.viendo', 'viendo…')];
  return ['mal', tA('agregar.motor.falta', '! falta entrar')];
}
/* Los pasos de un job para la persona: las 4 frases (job.humanos) o, si no vienen (varios cerebros), sus etiquetas */
function pasosDe(job) {
  var ol = el('ol', 'pasos7');
  var filas = (job && job.humanos) ? job.humanos.map(function (h) { return { st: h.st, t: h.texto }; })
    : ((job && job.pasos) || []).map(function (p) { return { st: p.st, t: p.label + (p.note ? ' — ' + p.note : '') }; });
  filas.forEach(function (f) {
    var li = el('li', f.st); li.appendChild(el('i', null, { ok: '✓', warn: '!', fail: '✗', skip: '–', run: '…' }[f.st] || '·'));
    li.appendChild(el('span', null, f.t)); ol.appendChild(li);
  });
  return ol;
}
/* Algo falló: una frase amable y, a pedido, lo que pasó de verdad (S7) */
function falloAmable(cont, titulo, texto, detalle) {
  var a = el('div', 'aviso mal'); a.appendChild(el('b', null, titulo)); a.appendChild(el('div', null, texto)); cont.appendChild(a);
  if (!detalle) return;
  var d = el('button', 'lnk', tA('agregar.boton.detalle', 'Ver detalle'));
  d.onclick = function () { d.remove(); cont.appendChild(el('div', 'pvacio', tA('agregar.err.detalle', 'Lo que pasó: {e}', { e: detalle }))); };
  cont.appendChild(d);
}
function crearAgente(modo) {
  var v = el('div', 'velo'), md = el('div', 'modal ca'); v.appendChild(md);
  var hd = el('div', 'mh'), tit = el('span', null, tA('agregar.titulo.nuevo', 'Agente nuevo')); hd.appendChild(tit); var x = el('button', 'cb'); x.appendChild(icono('x')); hd.appendChild(x); md.appendChild(hd);
  var bd = el('div', 'mb'), ft = el('div', 'mf'); md.appendChild(bd); md.appendChild(ft);
  var val = { nombre: '', ayuda: '', forma: FORMAS[Math.floor(Math.random() * FORMAS.length)], color: COLORES[Math.floor(Math.random() * COLORES.length)], motor: '' }, sondeo = null;
  x.onclick = function () { if (sondeo) return; v.remove(); };
  function formulario(error) {
    tit.textContent = tA('agregar.titulo.nuevo', 'Agente nuevo');
    bd.textContent = ''; ft.textContent = '';
    if (!val.motor) val.motor = motorInicial();
    var prev = el('div', 'prev'); bd.appendChild(prev);
    function vista(brinca) {
      prev.textContent = ''; prev.appendChild(monito(val.color, val.forma, 118));
      if (brinca) { var m = prev.firstChild; if (m && m.animate) m.animate([{ transform: 'translateY(0)' }, { transform: 'translateY(-10px)' }, { transform: 'translateY(0)' }], { duration: 420, easing: 'ease-out' }); }
    }
    var fi = el('div', 'formar'); bd.appendChild(fi);
    var n = el('input', 'nom'); n.value = val.nombre; n.placeholder = tA('agregar.ver.nombre_ph', 'ponle nombre'); n.maxLength = 40; n.spellcheck = false; fi.appendChild(n);
    var cmd = el('div', 'cmd'); fi.appendChild(cmd);
    var fs = el('div', 'fms'), cs = el('div', 'cls'); fi.appendChild(fs); fi.appendChild(cs);
    var ay = el('input', 'ayu'); ay.value = val.ayuda; ay.placeholder = tA('agregar.pagina.para_ph', '¿En qué te ayuda? (opcional)'); ay.maxLength = 600; ay.spellcheck = true; fi.appendChild(ay);
    ay.oninput = function () { val.ayuda = ay.value; };
    var mot = el('div', 'mots'); fi.appendChild(mot);
    var notaMot = el('div', 'pvacio'); fi.appendChild(notaMot);
    var ok = el('button', 'bt p', tA('agregar.boton.despertar', 'Despertar ↵').replace(' ↵', '')), no = el('button', 'bt', tA('agregar.boton.ya_tengo', 'Ya tengo un agente ›'));
    function pintaMotores() {
      mot.textContent = ''; notaMot.textContent = '';
      if (!S.motores.length) { notaMot.textContent = tA('agregar.motor.viendo_nota', 'Viendo qué motores tienes…'); return; }
      S.motores.filter(function (m) { return m.instalado || m.id === val.motor; }).forEach(function (m) {
        var e = estadoMotor(m), b = el('button', 'mot' + (m.id === val.motor ? ' on' : ''));
        b.appendChild(el('b', null, m.nombre || m.id)); b.appendChild(el('small', e[0], e[1]));
        b.onclick = function () { val.motor = m.id; pintaMotores(); };
        mot.appendChild(b);
      });
      var m = S.motores.filter(function (y) { return y.id === val.motor; })[0], nm = (m && m.nombre) || val.motor;
      if (!S.motores.some(function (y) { return y.instalado; })) notaMot.textContent = tA('agregar.motor.ninguno', 'No encontré ningún motor en esta computadora.') + ' ' + tA('agregar.motor.nota_ninguno', '');
      else if (m && !motorUsable(m) && m.estado !== 'verificando') notaMot.textContent = m.instalado ? tA('agregar.pagina.sin_sesion', 'Falta entrar a tu cuenta de {m}: lo creo igual y despierta cuando entres (Configuración → Motores).', { m: nm }) : tA('agregar.motor.nota_no_instalado', '{m} no está instalado.', { m: nm });
    }
    function pinta(brinca) {
      fs.textContent = ''; FORMAS.forEach(function (f) { var b = el('button', f === val.forma ? 'on' : ''); b.title = NOMBRES_FORMA[f]; b.appendChild(monito(val.color, f, 38, { quieto: true })); b.onclick = function () { if (val.forma === f) return; val.forma = f; pinta(true); }; fs.appendChild(b); });
      cs.textContent = ''; COLORES.forEach(function (c) { var b = el('button', c === val.color ? 'on' : ''); b.style.background = c; b.onclick = function () { if (val.color === c) return; val.color = c; pinta(true); }; cs.appendChild(b); });
      ok.style.background = val.color; ok.style.color = claroHex(val.color) ? '#151518' : '#fff'; ok.disabled = !comandoDe(val.nombre);
      pintaMotores(); vista(brinca);
    }
    function pintaCmd() { var c = comandoDe(val.nombre); cmd.textContent = c ? tA('agregar.nombre.ok', 'Su comando: {n}', { n: c }) : (val.nombre.trim() ? tA('agregar.nombre.invalido', 'Usa letras y números.') : ''); ok.disabled = !c; }
    n.oninput = function () { val.nombre = n.value; pintaCmd(); };
    n.onkeydown = function (e) { if (e.key === 'Enter' && !ok.disabled) ok.click(); };
    ay.onkeydown = function (e) { if (e.key === 'Enter' && !e.isComposing && !ok.disabled) ok.click(); };
    if (error) bd.appendChild(el('div', 'aviso mal', error));
    ok.onclick = function () {
      var c = comandoDe(val.nombre); if (!c) return n.focus();
      ok.disabled = true;
      post('/api/front/crear', { nombre: c, visible: val.nombre.trim().replace(/\s+/g, ' ').slice(0, 40), ayuda: val.ayuda.trim(), forma: val.forma, color: val.color, motor: val.motor || motorInicial() })
        .then(function (r) { val.sinSesion = !!r.sin_sesion; avance(r.job); }, function (e) {
          var cl = (e.datos || {}).clave;
          if (cl === 'localhost.err.crear_carpeta') return carpetaOcupada(c, e.message);
          formulario(e.message);
        });
    };
    no.onclick = function () { cargar(); };
    ft.appendChild(no); ft.appendChild(ok); pinta(false); pintaCmd(); setTimeout(function () { n.focus(); }, 0);
    if (!S.motores.length) cargarMotores().then(function () { if (bd.isConnected) { if (!val.motor || !S.motores.some(function (m) { return m.id === val.motor; })) val.motor = motorInicial(); pintaMotores(); } });
  }
  /* la carpeta ya existe: si es un agente, «Conectarlo» (sin tocar nada); si no, otro nombre */
  function carpetaOcupada(c, msg) {
    bd.textContent = ''; ft.textContent = '';
    bd.appendChild(el('div', 'sub', tA('agregar.err.carpeta.titulo', 'Ya hay una carpeta «{n}»', { n: val.nombre.trim() || c })));
    bd.appendChild(el('div', 'aviso', msg));
    var otro = el('button', 'bt', tA('agregar.boton.otro_nombre', 'Otro nombre')); otro.onclick = function () { formulario(); }; ft.appendChild(otro);
    var cn = el('button', 'bt p', tA('agregar.boton.conectarlo', 'Conectarlo ↵').replace(' ↵', ''));
    cn.onclick = function () { cargar(c); }; ft.appendChild(cn);
  }
  function avance(job) {
    bd.textContent = ''; ft.textContent = '';
    var mono = el('div'); mono.appendChild(monito(val.color, val.forma, 72)); bd.appendChild(mono);
    var visible = val.nombre.trim() || job.nombre;
    bd.appendChild(el('div', 'sub', tA('agregar.crea.titulo', 'Despertando a {n}…', { n: visible }) + (job.donde ? ' ' + job.donde : '')));
    bd.appendChild(pasosDe(job));
    if (!job.done) {
      var cx = el('button', 'bt', job.cancel ? '…' : tA('agregar.boton.cancelar', 'Cancelar')); cx.disabled = job.cancel;
      cx.onclick = function () { cx.disabled = true; post('/api/front/crear/cancelar', {}); };
      ft.appendChild(cx);
      sondeo = setTimeout(function () { api('/api/front/crear').then(function (r) { if (r.job) avance(r.job); }, function () { avance(job); }); }, 700);
      return;
    }
    sondeo = null;
    post('/api/front/crear/visto', {}).catch(function () {});
    if (!job.ok) {
      if (job.cancel) bd.appendChild(el('div', 'aviso mal', tA('agregar.err.cancelado', 'Cancelado: no quedó nada a medias.')));
      else falloAmable(bd, tA('agregar.err.fallo_titulo', 'No pude despertarlo.'), tA('agregar.err.fallo_texto', 'Algo falló mientras lo hacía. No quedó nada a medias: puedes intentarlo otra vez.'), job.error);
      var otra = el('button', 'bt p', tA('agregar.boton.atras', '‹ Atrás')); otra.onclick = function () { formulario(); }; ft.appendChild(otra);
      return;
    }
    var m = S.motores.filter(function (y) { return y.id === val.motor; })[0], nm = (m && m.nombre) || val.motor;
    bd.appendChild(el('div', 'aviso', val.sinSesion ? tA('agregar.hola.sin_sesion', 'Me falta {m}: inicia sesión en {m} para que despierte.', { c: job.nombre, m: nm }) : tA('agregar.hola.texto', 'Vivo en mi carpeta y pienso con {m}.', { c: job.nombre, m: nm })));
    var ir = el('button', 'bt p', tA('agregar.boton.conversar', 'Conversar ↵').replace(' ↵', ''));
    ir.onclick = function () { v.remove(); cargarInicio().then(function () { if (ag(job.nombre)) { elegirAgente(job.nombre); pintar(true); } }); };
    ft.appendChild(ir);
    cargarInicio().then(function () { pintarRiel(); });           // aparece en la barra
  }
  /* «Ya tengo un agente» (AG7-a): lo que encontré (con su monito) y la carpeta que pegas, con lo que trae */
  function cargar(conectarNombre) {
    tit.textContent = tA('agregar.titulo.cargar', 'Ya tengo un agente');
    bd.textContent = ''; ft.textContent = '';
    var lista = el('div', 'encs'); bd.appendChild(lista); lista.appendChild(el('div', 'pvacio', tA('agregar.cargar.buscando', 'Buscando en esta computadora…')));
    var masB = el('button', 'lnk', tA('agregar.cargar.protegidas', 'Buscar en Escritorio, Documentos y Descargas')); masB.style.display = 'none'; bd.appendChild(masB);
    bd.appendChild(el('div', 'pvacio', tA('agregar.cargar.pega', '¿No está? Pega o arrastra su carpeta aquí:')));
    var ruta = el('input', 'ayu'); ruta.placeholder = tA('agregar.cargar.ph', '~/…/la carpeta de tu agente'); ruta.spellcheck = false; bd.appendChild(ruta);
    var rad = el('div', 'pvacio'); bd.appendChild(rad);
    var atras = el('button', 'bt', tA('agregar.boton.atras', '‹ Atrás')), cn = el('button', 'bt p', tA('agregar.k.conectar', 'conectar'));
    cn.disabled = true; atras.onclick = function () { formulario(); }; ft.appendChild(atras); ft.appendChild(cn);
    var elegido = null, porRuta = null, tRuta = null;
    function pinta(d) {
      lista.textContent = '';
      var es = d.encontrados || [];
      lista.appendChild(el('div', 'sub', es.length ? (es.length === 1 ? tA('agregar.cargar.encontre_1', 'Encontré 1 en esta computadora') : tA('agregar.cargar.encontre', 'Encontré {n} en esta computadora', { n: es.length })) : tA('agregar.cargar.ninguno', 'No encontré agentes en esta computadora.')));
      es.forEach(function (e) {
        var b = el('button', 'enc' + (elegido === e.i ? ' on' : '')), ico = el('span', 'ico'); ico.appendChild(monito(e.color, e.forma, 30, { quieto: true }));
        b.appendChild(ico); b.appendChild(el('b', null, e.visible)); b.appendChild(el('small', null, e.corta));
        b.appendChild(el('em', e.estado, tA('agregar.cargar.est.' + e.estado, e.estado)));
        b.disabled = e.estado === 'cargado' || e.estado === 'incompleto';
        b.onclick = function () { elegido = e.i; porRuta = null; ruta.value = ''; rad.textContent = e.estado === 'incompleto' ? tA('agregar.carpeta.incompleto', '', { n: e.visible }) : ''; cn.disabled = false; cn.textContent = tA('agregar.boton.conectar_a', 'Conectar a {n} ↵', { n: e.visible }).replace(' ↵', ''); pinta(d); };
        if (conectarNombre && e.nombre === conectarNombre && !b.disabled) { conectarNombre = null; b.onclick(); }
        lista.appendChild(b);
      });
      masB.style.display = d.mac && !d.protegidas ? '' : 'none';
    }
    function buscar(prot) { api('/api/front/buscar' + (prot ? '?protegidas=1' : '')).then(pinta, function (e) { lista.textContent = ''; lista.appendChild(el('div', 'aviso mal', e.message)); }); }
    masB.onclick = function () { masB.disabled = true; buscar(true); };
    ruta.oninput = function () {
      elegido = null; porRuta = null; cn.disabled = true; clearTimeout(tRuta);
      var t = ruta.value.trim(); if (!t) { rad.textContent = ''; return; }
      tRuta = setTimeout(function () {
        api('/api/front/carpeta?ruta=' + encodeURIComponent(t)).then(function (r) {
          if (ruta.value.trim() !== t) return;
          rad.textContent = r.texto || '';
          if (r.veredicto === 'agente' || r.veredicto === 'choque') { porRuta = t; cn.disabled = false; cn.textContent = tA('agregar.boton.conectar_a', 'Conectar a {n} ↵', { n: r.visible || r.nombre }).replace(' ↵', ''); }
        }, function (e) { rad.textContent = e.message; });
      }, 300);
    };
    ruta.onkeydown = function (e) { if (e.key === 'Enter' && !cn.disabled) cn.click(); };
    cn.onclick = function () {
      cn.disabled = true;
      post('/api/front/cargar', porRuta ? { ruta: porRuta } : { indices: [elegido] }).then(function (r) { conectando(r.job); }, function (e) { rad.textContent = e.message; });
    };
    buscar(false); setTimeout(function () { ruta.focus(); }, 0);
  }
  function conectando(job) {
    bd.textContent = ''; ft.textContent = '';
    bd.appendChild(pasosDe(job));
    if (!job || !job.done) {
      sondeo = setTimeout(function () { api('/api/front/cargar').then(function (r) { conectando(r.job || job); }, function () { conectando(job); }); }, 600);
      return;
    }
    sondeo = null;
    post('/api/front/cargar/visto', {}).catch(function () {});
    var nombre = (job.nombres || [])[0], visible = nombre ? nombre.charAt(0).toUpperCase() + nombre.slice(1) : '';
    if (!job.ok) falloAmable(bd, tA('agregar.cargar.fallo_titulo', 'No pude conectarlo.'), tA('agregar.cargar.fallo_texto', 'Algo falló mientras lo conectaba. Su carpeta no cambió: puedes intentarlo otra vez.'), job.error);
    else bd.appendChild(el('div', 'aviso', (job.nombres || []).length > 1 ? tA('agregar.cargar.listos', '✓ Conecté {n} agentes.', { n: job.nombres.length }) : tA('agregar.cargar.listo', '✓ {n} ya está aquí.', { n: visible })));
    /* M2: si a su motor le falta tu sesión, lo mismo que dice crear (no «despierta») */
    if (job.ok && job.sin_sesion) bd.appendChild(el('div', 'pvacio', tA('agregar.hola.sin_sesion', 'Me falta {m}: inicia sesión en {m} para que despierte.', { c: nombre || '', m: job.motor || '' })));
    (job.avisos || []).slice(0, 2).forEach(function (a) { bd.appendChild(el('div', 'pvacio', tA('agregar.cargar.avisos', 'Ojo: {a}', { a: a }))); });
    var ir = el('button', 'bt p', job.ok ? tA('agregar.boton.conversar', 'Conversar ↵').replace(' ↵', '') : tA('agregar.boton.atras', '‹ Atrás'));
    ir.onclick = function () { if (!job.ok) return cargar(); v.remove(); cargarInicio().then(function () { if (nombre && ag(nombre)) { elegirAgente(nombre); pintar(true); } }); };
    ft.appendChild(ir);
    cargarInicio().then(function () { pintarRiel(); });
  }
  v.onclick = function (e) { if (e.target === v && !sondeo) v.remove(); };
  document.body.appendChild(v);
  var listos = TXA ? Promise.resolve() : api('/api/front/textos').then(function (r) { TXA = r.textos || {}; }, function () { TXA = {}; });
  listos.then(function () {
    if (modo === 'cargar') return cargar();
    api('/api/front/crear').then(function (r) { if (r.job && !r.job.done) avance(r.job); else formulario(); }, function () { formulario(); });
  });
}

/* ================= arranque ================= */
/* el panel NO se repinta en cada pintar(): cambiaría bajo tus dedos (y parpadeaba); solo cuando hace falta */
function pintar(conPanel) { pintarRiel(); pintarTop(); if (typeof pintarTabs === 'function') pintarTabs(); pintarHilo(); pintarActiva(); pintarSend(); if (conPanel) pintarPanel(); }
(function () {
  var ta = $('#ta');
  ta.addEventListener('input', function () { ta.style.height = 'auto'; ta.style.height = Math.min(180, ta.scrollHeight) + 'px'; pintarSend(); slash(); });
  ta.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && SLASH) { SLASH = null; cerrarCapas(); return; }
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && (!CFG_LOCAL.get('cmdEnter') || e.metaKey || e.ctrlKey)) {
      e.preventDefault(); var v = ta.value;
      /* §6: modelo y esfuerzo son botones; su selector ya no sale en el chat. «/model» y «/effort» abren la pastilla */
      if (/^\/(model|effort)(\s|$)/i.test(v.trim()) && activo()) { ta.value = ''; SLASH = null; cerrarCapas(); pintarSend(); panelAjustes($('#aj').style.display === 'none' ? $('#motor') : $('#aj'), activo()); return; }
      /* «/algo» que es una skill la activa; si no, va tal cual (los motores tienen sus propios comandos: /compact…) */
      if (v.charAt(0) === '/' && SLASH && SLASH[0] && v.indexOf(' ') < 0) { var p1 = SLASH[0], a = activo(); ta.value = ''; SLASH = null; cerrarCapas(); pintarSend(); if (a) activarSkill(a, p1.nombre); return; }
      SLASH = null; cerrarCapas();
      enviarCaja();
    }
  });
  $('#send').onclick = function () { enviarCaja(); };
  $('#fileIn').onchange = function () { adjuntar(this.files); this.value = ''; };
  prepararVoz(); prepararSoltar();
  document.addEventListener('keydown', teclasTabs);
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || SLASH || document.querySelector('.pop')) return;
    if (document.querySelector('.velo7')) return cerrarHoja();
    if (document.querySelector('.velo')) return document.querySelector('.velo').remove();
    var ae = document.activeElement; if (ae && /INPUT|TEXTAREA/.test(ae.tagName) && ae.value) return;
    if (S.EDIT) { if (S.EDIT.sucio) return nota('Guarda o descarta lo que editas primero', true); S.EDIT = null; return pintarPanel(); }
    if (S.PANEL) { S.PANEL = ''; pintarPanel(); pintarTop(); }
  });
  $('#mas').onclick = function (e) { e.stopPropagation(); menuMas(); };
  document.addEventListener('visibilitychange', function () { if (!document.hidden) sondeoChat(); });
  /* arranca: agentes y sus pestañas primero; lo demás llega solo */
  var intento = 0;
  function arrancar() {
    cargarInicio().then(function () { return Promise.all([cargarPestanas(), cargarMotores(), cargarSkills(), api('/api/v2/vivo?v=0').then(function (d) { VIVO.v = d.v; VIVO.e = d.e; restaurarTabs(); Object.keys(d.agentes || {}).forEach(function (id) { ponerFoto(id, d.agentes[id]); }); })]); })
      .then(function () {
        var a = activo(); if (a) cargarUsoSnap(a);
        Object.keys(S.vivo).forEach(function (id) { var f = S.vivo[id], x = ag(id); if (x) ponerEjecuciones(x, f.ejecuciones || []); });
        return a ? cargarConversacion(a) : null;
      })
      .then(function () { $('#col').textContent = ''; pintar(true); escuchar(); sondeoChat(); avisoApartadoPendiente(); setTimeout(guiaPrimeraVez, 700); setInterval(cargarSkills, 60000); setInterval(cargarMotores, 60000); setInterval(cargarInicio, 30000); setInterval(function () { var a = activo(); if (a) cargarUsoSnap(a); }, 30000); },
        function (e) {
          intento++;
          var C = $('#col'); C.textContent = ''; C.appendChild(el('div', 'vacio', 'No pude hablar con Workspace (' + e.message + '). Reintento en ' + Math.min(30, 2 * intento) + ' s…'));
          if (e.status === 403) { C.textContent = ''; C.appendChild(el('div', 'vacio', 'Esta página ya no tiene su llave. Ábrela otra vez desde el hub.')); return; }
          setTimeout(arrancar, Math.min(30, 2 * intento) * 1000);
        });
  }
  arrancar();
})();
