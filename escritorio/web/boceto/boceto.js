/* ===== boceto: arma el escritorio de ejemplo, la galería, la terminal y el recorrido =====
   El monito y su burbuja son WSM (escritorio/web/src) con el Monito de la página. Aquí solo se finge a Workspace:
   lo que en la app llega del puente (/api/v2), aquí lo manda un guion. */
(function () {
  /* los agentes con su forma y su color: los de tu Workspace si el armado los trae (build.py --agentes), o estos */
  var AG = (window.BOCETO_AGENTES || [
    { id: 'luna', n: 'Luna', c: '#ff4fa3', f: 'nube', motor: 'Claude Code' },
    { id: 'eco', n: 'Eco', c: '#ffffff', f: 'fantasma', motor: 'Codex' },
    { id: 'rio', n: 'Río', c: '#3fbf7f', f: 'nube', motor: 'OpenCode' },
    { id: 'tito', n: 'Tito', c: '#3b82f6', f: 'gatito', motor: 'Codex' },
    { id: 'mora', n: 'Mora', c: '#8b5cf6', f: 'gatito', motor: 'Cursor' }
  ]).slice(0, 5);
  while (AG.length < 5) AG.push(AG[AG.length - 1] || { id: 'luna', n: 'Luna', c: '#ff4fa3', f: 'nube', motor: '' });
  var A0 = AG[0].id;
  function agDe(id) { return AG.filter(function (a) { return a.id === id; })[0] || AG[0]; }
  var dormir = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var TOKEN = 0;                                        /* cambia cuando el recorrido se corta: lo que esperaba, se suelta */
  function vivo(tk) { if (tk !== TOKEN) throw new Error('corte'); }
  function ev(o) { WSM.recibir(o); }
  function elegido() { return WSM.s.elegido; }

  /* ---------- la hoja de ejemplo ---------- */
  var FILAS = [['Polanco', 1240500, 1300000], ['Coyoacán', 986200, 950000], ['Santa Fe', 1105800, 1200000], ['Condesa', 742300, 700000],
    ['Roma', 688900, 720000], ['Del Valle', 830100, 800000], ['Satélite', 611400, 650000], ['Interlomas', 902700, 880000],
    ['Tlalpan', 540800, 560000], ['Narvarte', 476300, 450000], ['Lindavista', 598200, 610000], ['Mixcoac', 512900, 500000],
    ['Pedregal', 1012400, 980000], ['Xochimilco', 402100, 430000]];
  var miles = function (n) { return n.toLocaleString('en-US'); };
  function hoja() {
    var H = document.getElementById('bcHoja'), cols = ['', 'A', 'B', 'C', 'D', 'E'];
    function c(t, cls) { var d = el('div', cls, t); H.appendChild(d); return d; }
    cols.forEach(function (k, i) { c(k, 'h' + (i > 3 ? ' x' + String.fromCharCode(64 + i) : '')); });
    c('1', 'n'); c('Sucursal', 't'); c('Ventas', 't num'); c('Con IVA', 't num colC'); c('Meta', 't num xD'); c('Avance', 't num xE');
    FILAS.forEach(function (f, i) {
      c(String(i + 2), 'n'); c(f[0]); c(miles(f[1]), 'num');
      var cc = c(miles(Math.round(f[1] * 1.16)), 'num colC'); cc.dataset.v = Math.round(f[1] * 1.16);
      c(miles(f[2]), 'num xD'); c(Math.round(f[1] / f[2] * 100) + ' %', 'num xE');
    });
  }
  function celdasC() { return [].slice.call(document.querySelectorAll('#bcHoja .colC')).slice(1); }
  function limpiarHoja() { celdasC().forEach(function (d) { d.textContent = miles(+d.dataset.v); d.classList.remove('sel', 'hecho'); }); }

  /* ---------- lo que contesta «Workspace» en el boceto ---------- */
  var GUION = null;                                     /* el recorrido pone aquí lo que sigue */
  WSM.alHost = function (op) {
    if (op.op === 'mandar' || op.op === 'responder') {
      if (GUION && GUION[op.op]) return GUION[op.op](op);
      if (!manual) return;
      respuestaLibre(op);
    } else if (op.op === 'permiso') {
      if (GUION && GUION.permiso) return GUION.permiso(op);
      if (manual) hacerTrabajo(++TOKEN, op.decision);
    }
  };
  var manual = false;
  async function escribir(texto, tk, cada) {
    var palabras = texto.split(/(\s+)/), t = '';
    for (var i = 0; i < palabras.length; i++) { vivo(tk); t += palabras[i]; if (palabras[i].trim()) { ev({ t: 'parcial', agente: elegido(), texto: t }); await dormir(cada || 70); } }
    return t;
  }
  async function respuestaLibre(op) {
    var tk = ++TOKEN, a = agDe(elegido());
    try {
      await dormir(1300); vivo(tk);
      var r = 'Te escucho. Esto es el boceto: en la app tu mensaje le llega a **' + a.n + '** por `/api/v2/mandar`, su motor (' + a.motor + ') lo trabaja y aquí ves su respuesta en vivo.';
      ev({ t: 'estado', agente: a.id, estado: 'pensando' });
      await escribir(r, tk); vivo(tk);
      ev({ t: 'respuesta', agente: a.id, texto: r }); ev({ t: 'estado', agente: a.id, estado: 'listo' });
      ev({ t: 'uso', agente: a.id, linea: 'Uso · 5 h: 62 % libre · contexto 18 %' });
    } catch (e) { }
  }
  async function hacerTrabajo(tk, decision) {
    var a = elegido();
    try {
      if (decision === 'negar') {
        await dormir(900); vivo(tk);
        var no = 'Va, no lo toco. Si quieres, te digo cómo hacerlo tú: **Formato → Número → Moneda**.';
        ev({ t: 'permiso', agente: a, id: null }); await escribir(no, tk); ev({ t: 'respuesta', agente: a, texto: no }); ev({ t: 'estado', agente: a, estado: 'listo' });
        return;
      }
      var cs = celdasC();
      ev({ t: 'pasos', agente: a, i: 0, n: 3, texto: 'Leyendo la hoja' });
      cs.forEach(function (d) { d.classList.add('sel'); });
      await dormir(1100); vivo(tk);
      ev({ t: 'permiso', agente: a, id: null });
      ev({ t: 'pasos', agente: a, i: 1, n: 3, texto: 'Cambiando el formato de la columna C' });
      for (var i = 0; i < cs.length; i++) { vivo(tk); cs[i].textContent = '$' + miles(+cs[i].dataset.v) + '.00'; cs[i].classList.remove('sel'); cs[i].classList.add('hecho'); await dormir(90); }
      ev({ t: 'pasos', agente: a, i: 2, n: 3, texto: 'Guardando' });
      await dormir(900); vivo(tk);
      ev({ t: 'pasos', agente: a, n: 0 });
      var fin = 'Listo: la columna C ya va en pesos, con dos decimales (' + cs.length + ' celdas). Dejé la nota en tu bitácora.';
      ev({ t: 'respuesta', agente: a, texto: fin }); ev({ t: 'estado', agente: a, estado: 'listo' });
      ev({ t: 'uso', agente: a, linea: 'Uso · 5 h: 61 % libre · contexto 21 %' });
    } catch (e) { }
  }

  /* ---------- el recorrido: un día normal con el monito, en ~25 s ---------- */
  function reiniciar() {
    TOKEN++; GUION = null;
    if (!WSM.s.agentes.length) WSM.agentes(AG, A0);         /* tras «Sin agentes» */
    WSM.barra(false);
    ev({ t: 'pregunta', id: null, agente: elegido() }); ev({ t: 'permiso', id: null, agente: elegido() }); ev({ t: 'pasos', n: 0, agente: elegido() });
    WSM.s.turno = null; WSM.s.aviso = null; WSM.s.uso = ''; WSM.s.permiso = null; WSM.s.pregunta = null; WSM.s.pasos = null;
    WSM.recibir({ t: 'estado', agente: elegido(), estado: 'reposo' });
    limpiarHoja();
  }
  function rect(id) { return document.getElementById(id).getBoundingClientRect(); }
  async function teclear(texto, tk) {
    var ta = document.querySelector('.wsm-caja textarea');
    for (var i = 1; i <= texto.length; i++) { vivo(tk); ta.value = texto.slice(0, i); ta.dispatchEvent(new Event('input')); await dormir(38 + Math.random() * 30); }
  }
  function enter() { document.querySelector('.wsm-caja textarea').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); }
  function pulsar(sel) { var b = document.querySelector(sel); if (b) { b.classList.add('si'); setTimeout(function () { b.click(); }, 380); } }
  async function recorrido() {
    manual = false; marcar('rec'); reiniciar();
    var tk = TOKEN;
    if (elegido() !== A0) WSM.elegir(A0, false);
    try {
      await dormir(2600); vivo(tk);
      var k = document.getElementById('bcKbd'); k.classList.remove('pulsa'); void k.offsetWidth; k.classList.add('pulsa');
      await dormir(300); vivo(tk); WSM.barra(true); marcar('escuchando');
      await dormir(600); await teclear('¿Dónde le cambio el formato a la columna C?', tk);
      await dormir(450); vivo(tk);
      var sigue = new Promise(function (ok) {
        GUION = {
          mandar: function () { ok(); },
          responder: function () { GUION.responder = null; ok2(); },
          permiso: function (op) { GUION = null; hacerTrabajo(tk, op.decision).then(okFin); }
        };
      });
      var ok2, okFin, respondio = new Promise(function (r) { ok2 = r; }), termino = new Promise(function (r) { okFin = r; });
      enter(); marcar('pensando');
      await sigue; await dormir(1500); vivo(tk);
      var r1 = 'Está en **Formato → Número**. Te lo enseño.';
      await escribir(r1, tk, 80); ev({ t: 'respuesta', agente: A0, texto: r1 });
      await dormir(500); vivo(tk); marcar('senalando');
      await WSM.senalar(rect('bcFormato'), 'Formato → Número', 2100); vivo(tk);
      ev({ t: 'pregunta', agente: A0, id: 'q1', texto: '¿Le pongo formato de moneda a toda la columna C?', opciones: ['Sí, a toda', 'Solo a las ventas', 'No'] });
      ev({ t: 'estado', agente: A0, estado: 'pregunta' }); marcar('pregunta');
      await dormir(2300); vivo(tk); pulsar('.wsm-tarjeta .chip.p');
      await respondio; marcar('pensando'); await dormir(1200); vivo(tk);
      ev({ t: 'permiso', agente: A0, id: 'p1', motor: AG[0].motor, opciones: ['permitir', 'permitir_siempre', 'negar'],
        texto: 'Quiere cambiar un archivo FUERA de su carpeta: «~/Documentos/Ventas_noviembre.xlsx».', ya: 'Quiso cambiar un archivo FUERA de su carpeta: «~/Documentos/Ventas_noviembre.xlsx».',
        detalle: 'Edit\n{"file_path": "~/Documentos/Ventas_noviembre.xlsx", "rango": "C2:C15", "formato": "$#,##0.00"}' });
      ev({ t: 'estado', agente: A0, estado: 'pregunta' }); marcar('permiso');
      await dormir(2800); vivo(tk); pulsar('.wsm-tarjeta .chip.p');
      await dormir(500); marcar('haciendo');
      await termino; vivo(tk); marcar('listo');
      await dormir(4200); vivo(tk);
      reiniciar(); recorrido();
    } catch (e) { }
  }

  /* ---------- los botones de estados (cortan el recorrido) ---------- */
  var ESTADOS = [['rec', 'Recorrido'], ['-'], ['reposo', 'Reposo'], ['escuchando', 'Escuchando'], ['pensando', 'Pensando'], ['senalando', 'Señalando', 'F1'],
    ['haciendo', 'Haciendo', 'F2'], ['listo', 'Listo'], ['-'], ['pregunta', 'Pregunta'], ['permiso', 'Permiso'], ['-'],
    ['enfrente', 'Lo que tienes enfrente', 'F0.5'], ['limpia', 'Respuesta limpia', 'F0.5'], ['aprendio', 'Aprendió', 'F0.5'],
    ['permisomac', 'Falta un permiso', 'F0.5'], ['seguido', 'Seguir en la página', 'F0.5'], ['sinagentes', 'Sin agentes', 'F0.5']];
  /* F0.5: con la forma de lo que contestó Claude Code en la prueba en vivo (21-nov; página de la rama, agente de prueba),
     con su 🧠, su --- y su menú de archivo, para que se vea cómo la burbuja los limpia. «foto» es literal; las demás,
     llevadas a la hoja de este escritorio de ejemplo (en vivo era un pull request en Safari) */
  var VIVO = {
    ver: 'Sí, acabo de leer tu ventana: estás en la hoja **Ventas_noviembre.xlsx**. La columna C trae las ventas con IVA y la E el avance contra la meta. ¿Te enseño dónde se exporta a PDF?\n\n🧠 check ✓ — leí su ventana actual',
    foto: 'No pude tomar la foto porque a tu Mac le falta darme el permiso de «Grabación de pantalla». El monito te está enseñando el botón para darlo; en cuanto lo actives, la tomo.\n\n🧠 check ✓ — falta permiso de pantalla',
    nota: 'Listo, te guardé la nota de la hoja en dos líneas y te salió la tarjeta para abrirla.\n\n---\n\n🧠 check ✓ — nota guardada desde ventana',
    skill: 'Te dejé el resumen de noviembre.\n\n```\n📄 deliverables/ventas/Resumen_nov_v1.md\n  1 — abrir el archivo        2 — revelar en Finder        3 — seguir con la conversación\n```\n\n🧠 Skill creada: `resumen-ventas` → `skills/datos/`'
  };
  var BOT = {};
  function marcar(k) { for (var x in BOT) BOT[x].classList.toggle('p', x === k); }
  function botones() {
    var N = document.getElementById('bcEstados');
    ESTADOS.forEach(function (e) {
      if (e[0] === '-') { N.appendChild(el('i', 'sep')); return; }
      var b = el('button', 'chip' + (e[0] === 'rec' ? ' rec' : ''));
      if (e[0] === 'rec') { b.appendChild(svgPlay()); }
      b.appendChild(document.createTextNode(e[1])); if (e[2]) b.appendChild(el('small', null, e[2]));
      b.onclick = function () { mostrar(e[0]); };
      BOT[e[0]] = b; N.appendChild(b);
    });
  }
  function svgPlay() { var s = NS('svg', { width: 12, height: 12, viewBox: '0 0 12 12' }); s.appendChild(NS('path', { d: 'M3 1.8v8.4L10 6z', fill: 'currentColor' })); return s; }
  async function mostrar(k) {
    if (k === 'rec') return recorrido();
    manual = true; reiniciar(); marcar(k); var tk = TOKEN, a = elegido();
    try {
      if (k === 'escuchando') { WSM.barra(true); await dormir(300); await teclear('Resume la hoja y mándamelo como nota', tk); }
      if (k === 'pensando') { WSM.s.turno = { tu: 'Resume la hoja y mándamelo como nota', texto: '', vivo: true }; ev({ t: 'estado', agente: a, estado: 'pensando' }); }
      if (k === 'senalando') await WSM.senalar(rect('bcFormato'), 'Formato → Número', 2600);
      if (k === 'haciendo') { WSM.s.turno = { tu: 'Ponle formato de moneda a la columna C', texto: '', vivo: false }; ev({ t: 'estado', agente: a, estado: 'haciendo' }); hacerTrabajo(tk, 'permitir'); }
      if (k === 'listo') {
        WSM.s.turno = { tu: 'Resume la hoja de ventas', texto: '' };
        ev({ t: 'respuesta', agente: a, texto: 'Noviembre va en **$10.65 M**, 3 % arriba de la meta. Polanco y Pedregal jalan; Xochimilco y Roma quedan abajo.' });
        ev({ t: 'estado', agente: a, estado: 'listo' }); ev({ t: 'uso', agente: a, linea: 'Uso · 5 h: 62 % libre · contexto 18 %' });
      }
      if (k === 'pregunta') {
        ev({ t: 'pregunta', agente: a, id: 'q2', texto: 'Leí la hoja (3 pestañas). ¿Lo guardo como nota en tu cerebro o te lo paso al correo?', opciones: ['Como nota', 'Al correo (borrador)', 'Nada'] });
        ev({ t: 'estado', agente: a, estado: 'pregunta' });
      }
      if (k === 'permiso') {
        ev({ t: 'permiso', agente: a, id: 'p2', motor: agDe(a).motor, opciones: ['permitir', 'permitir_siempre', 'negar'],
          texto: 'Quiere correr un comando: «python3 resumen.py ~/Documentos/Ventas_noviembre.xlsx».', ya: 'Quiso correr un comando: «python3 resumen.py ~/Documentos/Ventas_noviembre.xlsx».',
          detalle: 'Bash\n{"command": "python3 resumen.py ~/Documentos/Ventas_noviembre.xlsx", "description": "Resume la hoja"}' });
        ev({ t: 'estado', agente: a, estado: 'pregunta' });
      }
      if (k === 'enfrente') {
        WSM.contexto({ app: 'Hoja de cálculo', ventana: 'Ventas_noviembre.xlsx' }); WSM.barra(true);
        await dormir(300); await teclear('¿Dónde exporto esto a PDF?', tk);
      }
      if (k === 'limpia' || k === 'aprendio' || k === 'permisomac' || k === 'seguido') {
        var tu = { limpia: 'Guárdame una nota de 2 líneas con lo que viste', aprendio: 'Resúmeme la hoja en un archivo',
          permisomac: 'Mírala con una foto, por favor', seguido: '¿Puedes ver mi pantalla?' }[k];
        var r = { limpia: VIVO.nota, aprendio: VIVO.skill, permisomac: VIVO.foto, seguido: VIVO.ver }[k];
        WSM.s.turno = { tu: tu, texto: '', vivo: true }; ev({ t: 'estado', agente: a, estado: 'pensando' });
        ev({ t: 'respuesta', agente: a, texto: r, archivos: k === 'limpia' ? [{ ruta: 'notas/ventas-nov.md', titulo: 'Nota de ventas · noviembre' }] : [] });
        ev({ t: 'estado', agente: a, estado: 'listo' }); ev({ t: 'uso', agente: a, linea: 'Uso · gasto $0.24' });
        if (k === 'seguido') { await dormir(900); vivo(tk); ev({ t: 'seguido', agente: a, turnos: 4, abierta: true }); }
      }
      if (k === 'sinagentes') { WSM.agentes([]); WSM.barra(true); }
    } catch (e) { }
  }

  /* ---------- la galería: un monito por estado ---------- */
  var GAL = [
    ['reposo', 0, 'Reposo', '', 'Respira y parpadea en su esquina. Te sigue con los ojos.'],
    ['escuchando', 3, 'Escuchando', '', 'Mientras escribes en la barra: ojos grandes y atento a cada tecla.'],
    ['pensando', 2, 'Pensando', '', 'Su motor trabaja: lee de lado a lado, con sus tres puntos.'],
    ['senalando', 0, 'Señalando', 'F1', 'Vuela a un botón, lo ilumina y regresa. No toca nada.'],
    ['haciendo', 4, 'Haciendo', 'F2', 'Paso a paso y solo con tu OK. En F0, su motor usando herramientas.'],
    ['listo', 3, 'Listo', '', 'Festeja y deja la respuesta en su burbuja.'],
    ['pregunta', 2, 'Te espera', '', 'Una pregunta o un permiso: la tarjeta sale en su burbuja.'],
    ['duerme', 1, 'Dormido', '', 'Sin conexión con Workspace, o su motor está cerrado.']];
  var RAYA = { reposo: 'libre', escuchando: 'leyendo', pensando: 'pensando', senalando: 'escribiendo', haciendo: 'skill', listo: 'listo', pregunta: 'espera', duerme: 'dormido' };
  var MONO = { reposo: 'libre', escuchando: 'libre', pensando: 'trabaja', senalando: 'libre', haciendo: 'trabaja', listo: 'termino', pregunta: 'pregunta', duerme: 'duerme' };
  function galeria() {
    var G = document.getElementById('bcGal');
    GAL.forEach(function (g) {
      var a = AG[g[1]], card = el('div', 'bc-card'), esc = el('div', 'bc-esc2'), col = el('div', 'col');
      card.style.setProperty('--c', a.c);
      var m = new Monito(a.c, a.f, 64); m.setEstado(MONO[g[0]]);
      var w = el('div', 'wsm-yo'); w.appendChild(m.el); col.appendChild(w);
      var r = el('i', 'ray7 r-' + RAYA[g[0]]); r.style.setProperty('--c', a.c);
      if (g[0] === 'pensando') for (var i = 0; i < 3; i++) r.appendChild(el('b'));
      if (g[0] === 'haciendo') for (var j = 0; j < 3; j++) r.appendChild(el('b', j < 1 ? 'h' : j === 1 ? 'a' : ''));
      col.appendChild(r); esc.appendChild(col);
      if (g[0] === 'escuchando') {
        var mb = el('div', 'bc-mini-barra'), tx = el('span'); mb.appendChild(tx); mb.appendChild(el('i')); esc.appendChild(mb);
        escuchaSola(m, tx);
      }
      if (g[0] === 'senalando') { var bt = el('div', 'bc-mini-boton', 'Formato'); bt.style.setProperty('--c', a.c); esc.appendChild(bt); senalaSolo(m, w, bt); }
      if (g[0] === 'haciendo') { var ps = el('div', 'bc-mini-pasos'); for (var q = 0; q < 3; q++) ps.appendChild(el('b')); esc.appendChild(ps); pasosSolos(ps, r); }
      if (g[0] === 'listo') setInterval(function () { m.rafaga(6); }, 4600);
      card.appendChild(esc);
      var h = el('h3', null, g[2]); if (g[3]) h.appendChild(el('small', null, g[3])); card.appendChild(h);
      card.appendChild(el('p', null, g[4]));
      G.appendChild(card);
    });
  }
  function escuchaSola(m, tx) {
    var frase = 'resume la hoja y mándamelo…', i = 0;
    m.quieto = true; m.tabre = 1.16; m.tgx = -1; m.tgy = -4.2;
    setInterval(function () {
      i = i >= frase.length + 14 ? 0 : i + 1; tx.textContent = frase.slice(0, Math.min(i, frase.length));
      if (i > 0 && i <= frase.length) { m.gel.vel += (i % 2 ? 1 : -1) * 14; m.sy = .97; m.tabre = 1.16; if (Math.random() < .08) m.parpadea(); }
      else if (i === frase.length + 4) { m.tabre = 1; m.parpadea(true); }
    }, 90);
  }
  function senalaSolo(m, w, bt) {
    m.quieto = true;
    function ciclo() {
      /* a la izquierda del botón, a su altura (medido cada vez: la tarjeta cambia de ancho) */
      w.getAnimations().forEach(function (x) { x.cancel(); });
      var a = w.getBoundingClientRect(), b = bt.getBoundingClientRect();
      var dx = Math.round(b.left - 8 - a.right), dy = Math.round(b.top + b.height / 2 - (a.top + a.height * .6)), fin = 'translate(' + dx + 'px,' + dy + 'px)';
      m.tgx = 6; m.tgy = -2; m.salta(.9);
      w.animate([{ transform: 'translate(0,0)' }, { transform: 'translate(' + dx * .5 + 'px,' + (dy * .5 - 22) + 'px) rotate(-6deg)', offset: .5 }, { transform: fin }], { duration: 800, easing: 'cubic-bezier(.45,0,.25,1)', fill: 'forwards' });
      setTimeout(function () { m.modoOjo = 'feliz'; m.signo('exclama', { donde: 'der', esc: .75, sube: 8 }); }, 900);
      setTimeout(function () { m.modoOjo = 'normal'; m.tgx = -4; m.salta(.7); w.animate([{ transform: fin }, { transform: 'translate(0,0)' }], { duration: 650, easing: 'cubic-bezier(.45,0,.25,1)', fill: 'forwards' }); }, 2600);
    }
    ciclo(); setInterval(ciclo, 4200);
  }
  function pasosSolos(ps, r) {
    var p = 0;
    setInterval(function () {
      p = (p + 1) % 4;
      [ps, r].forEach(function (cont) { [].forEach.call(cont.children, function (b, j) { b.className = j < p ? 'h' : j === p ? 'a' : ''; }); });
    }, 1100);
  }

  /* ---------- la terminal: ws "…" ---------- */
  function linea(a) { return '<span class="ag" style="color:' + a.c + '">● ' + esc(a.n) + '</span>'; }
  var TERM = [
    ['$ ', 'ws "resume la hoja de ventas de noviembre"'],
    ['', linea(AG[0]) + ' <span class="gr">· pensando…</span>'],
    ['', 'Noviembre va en $10.65 M, 3 % arriba de la meta. Polanco y Pedregal jalan;\nXochimilco y Roma quedan abajo.'],
    ['', '<span class="gr">Uso · 5 h: 62 % libre · contexto 18 %</span>'],
    ['$ ', 'ws -a ' + AG[3].id + ' "¿qué falló en la prueba de anoche?"'],
    ['', linea(AG[3]) + ' <span class="am">te pide permiso:</span> Quiere correr un comando: «python3 tests/run.py».'],
    ['', '  <span class="gr">[p] Permitir · [s] Siempre · [n] No ›</span> p'],
    ['', 'Falló test_arranque: el puerto 9121 ya estaba ocupado. Ya lo liberé y volvió a pasar.']];
  async function terminal() {
    var P = document.getElementById('bcTermTxt');
    while (true) {
      P.textContent = ''; var hecho = '';
      for (var i = 0; i < TERM.length; i++) {
        var l = TERM[i];
        if (l[0]) {
          for (var k = 0; k <= l[1].length; k++) { pintar(P, hecho + '<span class="pr">$ </span>' + esc(l[1].slice(0, k)) + '<span class="cur"></span>'); await dormir(32); }
          hecho += '<span class="pr">$ </span>' + esc(l[1]) + '\n'; await dormir(500);
        } else { hecho += l[1] + '\n'; pintar(P, hecho + '<span class="cur"></span>'); await dormir(i === 1 || i === 5 ? 1300 : 700); }
      }
      await dormir(5200);
    }
  }
  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
  /* el texto de la terminal es fijo (de este archivo): se arma con DOMParser, no con innerHTML */
  var _DP = new DOMParser();
  function pintar(P, html) {
    var d = _DP.parseFromString('<pre>' + html + '</pre>', 'text/html').body.firstChild;
    P.textContent = ''; while (d.firstChild) P.appendChild(d.firstChild);
  }

  /* ---------- ⌥ Espacio también aquí ---------- */
  document.addEventListener('keydown', function (e) {
    if (e.altKey && (e.code === 'Space' || e.key === ' ')) { e.preventDefault(); manual = true; TOKEN++; marcar('escuchando'); WSM.barra(); }
  });

  hoja(); botones();
  WSM.montar(document.getElementById('wsm'));
  WSM.agentes(AG, A0);
  galeria(); terminal();
  /* para las capturas: #estado=<k> enseña ese estado (sin el recorrido) */
  var pedido = /[#&]estado=([a-z]+)/.exec(location.hash || '');
  if (pedido && BOT[pedido[1]]) { document.documentElement.classList.add('bc-captura'); setTimeout(function () { mostrar(pedido[1]); }, 400); }
  else recorrido();
  window.BC = { mostrar: mostrar, recorrido: recorrido };
})();
