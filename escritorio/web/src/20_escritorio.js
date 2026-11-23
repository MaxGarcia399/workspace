/* ================= el monito de escritorio =================
   Vive en su lugar de la pantalla, animado y quieto, hasta que lo llamas (⌥ Espacio o un clic). Es el MISMO monito de
   la página (Monito, de 10_monitos.js): la forma y el color de cada agente, sus ojos, su rayita y sus gestos.
   Lo que ves aquí lo dice Workspace: este archivo solo pinta. Lo que haces (mandar, contestar, permitir) sale por
   `host` a quien lo cargó: la app de la Mac (webkit.messageHandlers.ws → escritorio/puente.py → /api/v2) o el boceto.
   Estados: reposo · escuchando · pensando · señalando · haciendo · listo, más pregunta, error y duerme.
   Modo escritorio (F0.5): la conversación es la del ESCRITORIO de cada agente (aparte de la de la página). Lo que dice
   se limpia con la regla de la página (15_texto.js: sin 🧠, sin menú de archivo, sin ---); sus archivos son tarjetas
   que se abren por el puente (nunca desde aquí); lo que tenías enfrente va en un chip que se quita con ✕ (D3-a);
   «Seguir en la página» lleva el hilo a la página; un archivo que sueltas en el monito viaja con tu mensaje.
   Movimiento (sin saltos ni brincos dobles): cada pieza tiene UN dueño por propiedad. Las entradas y salidas son de su
   clase (transform y opacidad, en el CSS); lo que se recorre porque algo cambió debajo, de `acomodar` (la propiedad
   `translate`); lo que crece o se encoge, también de `acomodar` (la propiedad `height`). Lo que ya se ve no se vuelve a
   animar, y con «reducir movimiento» nada se mueve: aparece. El monito se arrastra: la app de la Mac toma el ratón en
   su nido (nativo, sin pasar por aquí) y mueve la ventana; aquí solo se levanta y baja (WSM.agarrar), lo que tiene
   abierto se va con él, un clic sin moverse lo llama (WSM.clicNido) y, si al soltarlo cambia hacia dónde abre
   (WSM.lado), la burbuja se muda con el monito quieto (WSM.mudanza). */
/* ================= la plática: cómo se ve un mensaje (una sola hechura para la burbuja y para el chat grande) =========
   Ronda 2 · bloques C y G. La burbuja y el chat grande son EL MISMO chat en dos tamaños: aquí viven sus piezas puras
   (sin estado): el texto con formato, la línea gris de «lo que hizo», la hora y el día.
   De la página se usa tal cual lo que el armado trae (web/front/src/50_chat.js): texto() para `código`, **negritas** y
   bloques ```, y resumenHerr() para juntar «lo que hizo» en una línea («leyó 3 archivos · corrió un comando»). Lo que la
   página no tiene y aquí hace falta: listas, títulos y enlaces.
   Un enlace NUNCA es un <a>: se ve la dirección en texto y un botón «Abrir», que sale por el `host` (la app decide con
   la regla del portero si esa dirección se abre o solo se copia). Nada se abre desde aquí. */
var WSM_PLATICA = (function () {
  /* las herramientas del monito (escritorio/manos_mcp.py), en palabras de todos los días */
  var MANOS = { leer_ventana: 'leyó tu ventana', ver_pantalla: 'vio tu ventana', senalar: 'señaló 1 lugar',
    contexto_escritorio: 'vio qué tienes enfrente', actuar: 'hizo 1 cosa con tu OK', encargar: 'te propuso un encargo',
    mostrar_archivo: 'te enseñó 1 archivo', reportar_avance: 'contó su avance' };
  var MANOS_PL = { 'leyó tu ventana': 'leyó tu ventana {n} veces', 'vio tu ventana': 'vio tu ventana {n} veces',
    'señaló 1 lugar': 'señaló {n} lugares', 'vio qué tienes enfrente': 'vio qué tienes enfrente {n} veces',
    'hizo 1 cosa con tu OK': 'hizo {n} cosas con tu OK', 'abrió 1 página': 'abrió {n} páginas', 'abrió 1 cosa': 'abrió {n} cosas',
    'te propuso un encargo': 'te propuso {n} encargos', 'te enseñó 1 archivo': 'te enseñó {n} archivos', 'contó su avance': 'contó su avance {n} veces' };
  var DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
  var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  function nodo(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
  /* las tablas de la página aprenden los plurales del monito (solo en esta copia: la página no cambia) */
  try { if (typeof HERR_PL === 'object' && HERR_PL) for (var k0 in MANOS_PL) if (!HERR_PL[k0]) HERR_PL[k0] = MANOS_PL[k0]; } catch (e) { }

  /* ---------- el texto ---------- */
  /* `código` y **negritas**: con texto() de la página si el armado la trae; si no (una prueba suelta), lo mismo aquí */
  function corrido(n, s) {
    if (!s) return;
    if (typeof texto === 'function' && s.indexOf('```') < 0) { texto(n, s); return; }
    String(s).split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/).forEach(function (p) {
      if (!p) return;
      if (p.length > 2 && p[0] === '`') n.appendChild(nodo('code', null, p.slice(1, -1)));
      else if (p.length > 4 && p.slice(0, 2) === '**') n.appendChild(nodo('b', null, p.slice(2, -2)));
      else n.appendChild(document.createTextNode(p));
    });
  }
  var RE_EN = /(`[^`\n]+`)|\[([^\]\n]{1,200})\]\((https?:\/\/[^\s)]{1,2000})\)|(https?:\/\/[^\s<>"'`\])]+)/g;
  function dominio(u) { var m = /^https?:\/\/([^\/?#:]+)/i.exec(u); return m ? m[1].replace(/^www\./i, '') : u; }
  /* la dirección, en texto y sin esconder nada: entera si es corta; si es larga, su sitio y el principio de su camino */
  function direccion(u) {
    var s = String(u).replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/$/, '');
    return s.length > 46 ? s.slice(0, 43) + '…' : s;
  }
  function enlace(etq, url, abrir) {
    var w = nodo('span', 'wsm-enlace');
    if (etq && etq !== url) w.appendChild(nodo('span', 't', etq));
    var d = nodo('span', 'dir', direccion(url)); d.title = url; w.appendChild(d);
    var b = nodo('button', 'ir', 'Abrir'); b.title = 'Abrir ' + dominio(url) + ' en tu navegador';
    b.onclick = function (e) { if (e && e.stopPropagation) e.stopPropagation(); if (abrir) abrir(url, b); };
    w.appendChild(b);
    return w;
  }
  function enLinea(n, s, abrir) {
    s = String(s || '').replace(/\*\*(\[[^\]\n]{1,200}\]\(https?:\/\/[^\s)]{1,2000}\))\*\*/g, '$1');
    var i = 0, m; RE_EN.lastIndex = 0;
    while ((m = RE_EN.exec(s))) {
      if (m[1]) continue;                                   /* una dirección dentro de `código` es texto */
      var url = m[3] || m[4], cola = '';
      if (m[4]) { var c = /[.,;:!?…]+$/.exec(url); if (c) { cola = c[0]; url = url.slice(0, -cola.length); } }
      corrido(n, s.slice(i, m.index));
      n.appendChild(enlace(m[2] || '', url, abrir));
      if (cola) n.appendChild(document.createTextNode(cola));
      i = m.index + m[0].length;
    }
    corrido(n, s.slice(i));
  }
  var RE_ITEM = /^(\s*)(?:([-*•])|(\d{1,3})[.)])\s+(.*)$/, RE_TIT = /^\s{0,3}#{1,4}\s+(.*?)\s*#*\s*$/;
  function bloques(raiz, parte, abrir) {
    var lineas = String(parte).split('\n'), p = null, lista = null, li = null;
    function cierra() { p = null; lista = null; li = null; }
    lineas.forEach(function (l) {
      if (!l.trim()) { cierra(); return; }
      var t = RE_TIT.exec(l);
      if (t) { cierra(); var h = nodo('p', 'tit'); enLinea(h, t[1], abrir); raiz.appendChild(h); return; }
      var m = RE_ITEM.exec(l);
      if (m) {
        var tipo = m[3] ? 'ol' : 'ul';
        if (!lista || lista._tipo !== tipo) { p = null; lista = nodo(tipo); lista._tipo = tipo; if (m[3] && m[3] !== '1') lista.setAttribute('start', m[3]); raiz.appendChild(lista); }
        li = nodo('li', m[1].length >= 2 ? 'sub' : ''); enLinea(li, m[4], abrir); lista.appendChild(li);
        return;
      }
      if (li && /^\s{2,}\S/.test(l)) { li.appendChild(document.createTextNode(' ')); enLinea(li, l.trim(), abrir); return; }   /* sigue su renglón */
      lista = null; li = null;
      if (!p) { p = nodo('p'); raiz.appendChild(p); } else p.appendChild(document.createTextNode('\n'));
      enLinea(p, l, abrir);
    });
  }
  /* lo que escribió el agente → párrafos, listas, títulos, código y enlaces (sin HTML suyo: todo es texto) */
  function md(raiz, s, abrir) {
    raiz.textContent = '';
    String(s || '').split('```').forEach(function (parte, i) {
      if (i % 2) { raiz.appendChild(nodo('pre', null, parte.replace(/^[a-zA-Z0-9_-]*\n/, '').replace(/\n$/, ''))); return; }
      bloques(raiz, parte, abrir);
    });
    return raiz;
  }
  /* el mismo texto, sin sus marcas (para una línea corta: el globito, «Copiar todo») */
  function plano(s) {
    return String(s || '').replace(/```[a-zA-Z0-9_-]*\n?/g, '').replace(/\*\*([^*\n]+)\*\*/g, '$1').replace(/`([^`\n]+)`/g, '$1')
      .replace(/\[([^\]\n]{1,200})\]\((https?:\/\/[^\s)]{1,2000})\)/g, '$1 ($2)').replace(/^\s{0,3}#{1,4}\s+/gm, '');
  }

  /* ---------- lo que hizo: una línea gris que se abre ---------- */
  function corto(n) {
    n = String(n || '');
    for (var k in MANOS) if (n === k || n.slice(-(k.length + 1)) === '_' + k || n.slice(-(k.length + 1)) === '.' + k || n.slice(-(k.length + 1)) === '/' + k) return k;
    return '';
  }
  function frase(x) {
    var k = corto(x && x.n);
    if (!k) return String((x && x.n) || '');
    if (k === 'actuar' && /abrir/i.test(String(x.d || ''))) return /https?:/i.test(String(x.d)) ? 'abrió 1 página' : 'abrió 1 cosa';
    return MANOS[k];
  }
  function resumen(h) {
    var hh = (h || []).filter(function (x) { return x && x.n; }).map(function (x) { return { n: frase(x), d: x.d }; });
    if (!hh.length) return '';
    var t;
    if (typeof resumenHerr === 'function') t = resumenHerr(hh);
    else {                                                   /* sin la página (una prueba suelta): lo mismo, en corto */
      var orden = [], cuenta = {};
      hh.forEach(function (x) { if (!cuenta[x.n]) { cuenta[x.n] = 0; orden.push(x.n); } cuenta[x.n]++; });
      t = orden.map(function (n) { return cuenta[n] > 1 ? (MANOS_PL[n] || n + ' ×{n}').replace('{n}', cuenta[n]) : n; }).slice(0, 3).join(' · ')
        + (orden.length > 3 ? ' y ' + (orden.length - 3) + ' más' : '');
    }
    /* cada cosa que hizo, con mayúscula («Leyó tu ventana · Señaló 1 lugar») */
    return t.split(' · ').map(function (x) { return x.charAt(0).toUpperCase() + x.slice(1); }).join(' · ');
  }
  /* h: [{n: herramienta, d: detalle}] → la línea («Leyó tu ventana · Señaló 1 lugar»); un clic enseña cuáles. null si no hizo nada */
  function hizo(h) {
    var t = resumen(h); if (!t) return null;
    var w = nodo('div', 'wsm-hizo'), b = nodo('button', 'linea'), lista = null;
    b.appendChild(nodo('i', 'fl')); b.appendChild(nodo('span', null, t)); b.title = 'Ver qué hizo';
    b.onclick = function (e) {
      if (e && e.stopPropagation) e.stopPropagation();
      if (lista) { lista.remove(); lista = null; w.className = 'wsm-hizo'; return; }
      lista = nodo('div', 'cuales', (h || []).filter(function (x) { return x && x.n; }).map(function (x) {
        var k = corto(x.n), f = frase(x), nom = (typeof HERR_N === 'object' && HERR_N[x.n]) || f;
        return nom.charAt(0).toUpperCase() + nom.slice(1) + (x.d && !k ? ' · ' + String(x.d).slice(0, 120) : '');
      }).join('\n'));
      w.appendChild(lista); w.className = 'wsm-hizo abierta';
    };
    w.appendChild(b);
    return w;
  }

  /* ---------- la hora y el día ---------- */
  function fecha(t) { var d = new Date((+t || 0) * 1000); return isNaN(d.getTime()) ? null : d; }
  function dos(n) { return (n < 10 ? '0' : '') + n; }
  function hora(t) { var d = fecha(t); return d && +t ? d.getHours() + ':' + dos(d.getMinutes()) : ''; }
  function clave(d) { return d.getFullYear() * 10000 + d.getMonth() * 100 + d.getDate(); }
  /* «Hoy», «Ayer» o «lun 18 nov» (t y ahora, en segundos) */
  function dia(t, ahora) {
    var d = fecha(t); if (!d || !+t) return '';
    var h = fecha(ahora) || new Date(), ay = new Date(h.getTime() - 86400000);
    if (clave(d) === clave(h)) return 'Hoy';
    if (clave(d) === clave(ay)) return 'Ayer';
    return DIAS[d.getDay()] + ' ' + d.getDate() + ' ' + MESES[d.getMonth()] + (d.getFullYear() !== h.getFullYear() ? ' ' + d.getFullYear() : '');
  }
  /* la plática entera en texto («Copiar todo»): quién dijo qué, en orden, sin marcas */
  function todo(turnos, quien) {
    return (turnos || []).filter(function (x) { return x && (x.texto || '').trim() && x.rol !== 'nota'; }).map(function (x) {
      return (x.rol === 'yo' ? 'Tú' : quien || 'Agente') + ': ' + plano(x.texto).trim();
    }).join('\n\n');
  }
  return { md: md, plano: plano, hizo: hizo, resumen: resumen, hora: hora, dia: dia, todo: todo, enlace: enlace, dominio: dominio };
})();

var WSM = (function () {
  var MONO_DE = { reposo: 'libre', escuchando: 'libre', pensando: 'trabaja', senalando: 'libre', haciendo: 'trabaja',
    listo: 'termino', pregunta: 'pregunta', error: 'error', duerme: 'duerme' };
  /* la rayita bajo el monito. UN solo indicador a la vez: cuando el monito ya dice algo con su propio signo (sus tres
     puntitos al trabajar, su «?» al preguntar), la rayita se queda quieta; solo habla cuando trae algo que el monito no
     dice (los pasos de una skill: entonces el monito guarda sus puntitos). Mientras mira tu pantalla, el ojito es el
     indicador. */
  var RAYA_DE = { reposo: 'libre', escuchando: 'leyendo', pensando: 'libre', senalando: 'escribiendo', haciendo: 'libre',
    listo: 'listo', pregunta: 'libre', error: 'error', duerme: 'dormido' };
  var TXT = { reposo: '', escuchando: 'te escucha', pensando: 'pensando', senalando: 'te enseña', haciendo: 'trabajando',
    listo: 'terminó', pregunta: 'te espera', error: 'se atoró', duerme: 'dormido' };
  var VIVOS = { pensando: 1, haciendo: 1, escuchando: 1, senalando: 1 };
  /* trabaja de verdad (no solo te escucha o te enseña): el monito hace su gesto de trabajo */
  var TRABAJA = { pensando: 1, haciendo: 1 };
  /* los estados en que su motor NO está escribiendo: el ▮ de «escribiendo» se apaga (y no se vuelve a prender solo) */
  var QUIETOS = { listo: 1, reposo: 1, error: 1, duerme: 1, pregunta: 1 };
  var PX = 76, MAX_ADJUNTO = 20 * 1024 * 1024;
  /* un clic que se mueve más que esto ya es arrastrar al monito */
  var UMBRAL_ARRASTRE = 5;
  /* lo que se ve de la plática de antes (lo demás, en la página) */
  var HILO_MAX = 14;
  /* en el chat grande cabe más plática */
  var HILO_GRANDE = 80;
  /* la caja de escribir crece hasta 5 renglones (C3) y luego se recorre */
  var RENGLON = 22, RENGLONES = 5, CAJA_MIN = 28, CAJA_MAX = RENGLON * RENGLONES + 6;
  var MODO = 'wsm.modo';
  /* el contrato con la app de la Mac: si la app es de antes, algunos botones no le llegan (se dice, no se calla) */
  var CONTRATO = 3;
  var SIN_AGENTES = 'Todavía no tienes agentes. Crea el primero en la página de Workspace y aquí aparece.';
  var APP_VIEJA = 'Mi ventana es nueva pero mi app es de antes, así que algunos botones no me van a responder. '
    + 'Ciérrame y vuelve a abrirme (desde mi carita, arriba en la barra: «Cerrar Workspace Compañero»).';
  var EN_FILA = 'Lo tiene en fila: te contesta en cuanto termine lo que está haciendo.';
  var S = { agentes: [], elegido: '', estado: 'duerme', antes: 'reposo', barra: false, turno: null, pregunta: null,
    permiso: null, pasos: null, hace: '', uso: '', aviso: null, responde: null, vuela: false,
    ctx: null, ctxFuera: false, adjuntos: [], conAgentes: null, sinManos: '', lado: { h: 'der', v: 'abajo' },
    arrastra: false, agarrado: false, hilos: {}, hiloDe: {}, cambios: null, platicar: false, licencia: null, app: null, appVieja: false,
    /* ronda 2 · el chat grande: `grande` = esta ventana pinta el chat en grande (las MISMAS piezas, acomodadas);
       `fuera` = el grande está abierto en su propia ventana (esta burbuja se calla); `modo` = cómo lo dejaste */
    grande: false, fuera: false, modo: 'chico', nuevo: false, busca: '', hallados: [], hallaI: -1, rec: null };

  /* la tarjeta de permiso de su motor vive en 19_permiso.js (WSMPermiso: su ciclo y lo que pinta) */
  var CICLO = WSMPermiso.ciclo;
  var PERM = CICLO.nuevo();
  function ahoraMs() { return Date.now(); }
  var R = {}, MONO = null, ZONAS = '';

  function enApp() { return document.documentElement.classList.contains('wsm-app'); }
  function ent() { return typeof WSMEntregas !== 'undefined'; }
  function host(op) {
    if (W.alHost) { try { W.alHost(op); } catch (e) { } return; }
    try { window.webkit.messageHandlers.ws.postMessage(op); } catch (e) { }
  }
  function ag(id) { for (var i = 0; i < S.agentes.length; i++) if (S.agentes[i].id === id) return S.agentes[i]; return null; }
  function actual() { return ag(S.elegido) || S.agentes[0] || { id: '', n: 'Workspace', c: '#ffffff', f: 'bolita' }; }
  function contraste(c) { return claroHex(c) ? '#151518' : '#ffffff'; }
  function limpio(a) {
    var c = /^#[0-9a-fA-F]{6}$/.test(a.c || '') ? a.c.toLowerCase() : '#ffffff';
    var x = { id: String(a.id || ''), n: String(a.n || a.nombre || a.id || ''), c: c, f: FORMAS.indexOf(a.f) >= 0 ? a.f : 'bolita',
      motor: String(a.motor || '') };
    /* Fable v2: lo que dice «Pásaselo a…» de su nivel (lo arma la app con datos de Workspace: textos, nada que corra) */
    if (a.encargo && typeof a.encargo === 'object') {
      var n = a.encargo, t = function (v) { return typeof v === 'string' ? v.slice(0, 300) : ''; };
      x.encargo = { acotado: n.acotado === true, base: t(n.base), sin: t(n.sin), comandos: t(n.comandos), internet: t(n.internet),
        pagina: t(n.pagina), aviso: t(n.aviso),
        casillas: (Array.isArray(n.casillas) ? n.casillas : []).filter(function (c) { return Array.isArray(c) && ['comandos', 'internet', 'como_pagina'].indexOf(c[0]) >= 0; })
          .map(function (c) { return [c[0], t(c[1])]; }) };
    }
    if (Array.isArray(a.lo_lee)) x.lo_lee = a.lo_lee.slice(0, 2).map(function (v) { return String(v || '').slice(0, 80); });
    return x;
  }

  /* texto con `código` y **negritas**, sin HTML */
  function md(nodo, s) { WSM_PLATICA.md(nodo, s, abrirEnlace); }
  /* «Abrir» en un enlace: sale por el host (la app revisa la dirección con la regla del portero: la abre en tu
     navegador o, si lleva datos o es rara, solo te la copia). Lo que pasó vuelve en una línea ({t: 'enlace'}). */
  function abrirEnlace(url, b) {
    if (b) { b.disabled = true; setTimeout(function () { b.disabled = false; }, 1500); }
    var o = { op: 'abrir_enlace', agente: actual().id, url: String(url).slice(0, 2000) };
    /* M-3/M-5: el marco del botón (la app comprueba que tu clic fue sobre él) */
    try { var r = b.getBoundingClientRect(); o.r = [r.left, r.top, r.width, r.height]; } catch (e) { }
    host(o);
  }

  /* ---------- el movimiento: un dueño por propiedad ---------- */
  var SUAVE = 'cubic-bezier(.2,.8,.2,1)', T_ACOMODO = 260;
  function quieto() {
    try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (e) { return false; }
  }
  function anima(n) { return !!(n && typeof n.animate === 'function' && typeof n.offsetHeight === 'number') && !quieto(); }
  function visible(n) {
    return !!(n && !n.hidden && n.offsetParent && !(n.classList && (n.classList.contains('saliendo') || n.classList.contains('sale'))));
  }
  /* lo que se apila junto al nido: la burbuja, la barra y lo de las manos (tarjeta de la Mac y el ojito) */
  function pila() { return [R.globo, R.barra, R.manos].filter(visible); }
  /* las tarjetas de las manos (cambian de alto cuando cambia su texto) */
  function cartas() { return R.manos ? [].slice.call(R.manos.children || []).filter(visible) : []; }
  function corrido(n) {
    if (!n._flip) return 0;
    try { var m = /(-?[\d.]+)px\s+(-?[\d.]+)px/.exec(getComputedStyle(n).translate || ''); return m ? +m[2] : 0; } catch (e) { return 0; }
  }
  /* El borde del lado del nido (abajo, o arriba si la burbuja abre hacia abajo), en la pantalla: la caja crece hacia
     el otro lado, así que se mide desde la ventana y no desde la caja */
  function borde(n) {
    var t = R.raiz.getBoundingClientRect().top + n.offsetTop;
    return S.lado.v === 'arriba' ? t : t + n.offsetHeight;
  }
  /* `cambio()` toca el DOM; lo que se recorrió o cambió de alto por eso llega a su lugar deslizándose (FLIP), sin
     brincar. Si ya se estaba deslizando, sigue desde donde iba (nunca vuelve a empezar). */
  function acomodar(cambio) {
    if (S.grande || !anima(R.raiz)) { cambio(); return; }
    var antes = [];
    pila().concat(cartas()).forEach(function (n) { antes.push([n, borde(n) + corrido(n), n.offsetHeight]); });
    antes.forEach(function (x) {
      var n = x[0];
      if (n._flip) { n._flip.cancel(); n._flip = null; }
      if (n._alto) { n._alto.cancel(); n._alto = null; n.classList.remove('midiendo'); }
    });
    cambio();
    /* primero lo que cambia de alto (empieza en su alto de antes: lo de alrededor se queda donde estaba)… */
    antes.forEach(function (x) {
      var n = x[0], h = visible(n) ? n.offsetHeight : 0;
      if (h && (n === R.globo || n === R.barra || n.parentNode === R.manos) && Math.abs(x[2] - h) > 1) {
        n.classList.add('midiendo');
        n._alto = n.animate([{ height: x[2] + 'px' }, { height: h + 'px' }], { duration: 220, easing: SUAVE });
        n._alto.onfinish = function () { n._alto = null; n.classList.remove('midiendo'); };
      }
    });
    /* …y luego lo que se recorrió, medido ya con esos altos (si no, se movía dos veces) */
    antes.forEach(function (x) {
      var n = x[0]; if (!visible(n) || n.parentNode === R.manos) return;
      var d = x[1] - borde(n);
      if (Math.abs(d) > .5) {
        n._flip = n.animate([{ translate: '0 ' + d + 'px' }, { translate: '0 0' }], { duration: T_ACOMODO, easing: SUAVE });
        n._flip.onfinish = function () { n._flip = null; };
      }
    });
  }
  /* termina cuando acaba su animación de salida, o a los `ms` si el navegador no avisa */
  function alTerminar(n, ms, fn) {
    var hecho = false, t;
    function fin(e) { if (e && e.target !== n) return; if (hecho) return; hecho = true; clearTimeout(t); n.removeEventListener && n.removeEventListener('animationend', fin); fn(); }
    if (n.addEventListener) n.addEventListener('animationend', fin);
    t = setTimeout(fin, ms);
  }
  /* Una pieza sale: deja su hueco al momento (lo de alrededor se acomoda deslizándose) y se desvanece en su lugar.
     `fin` la esconde. Si vuelve a entrar mientras sale (otraVez), se queda sin volver a animarse. */
  function salir(n, ms, fin) {
    if (!anima(n) || !visible(n)) { fin(); return; }
    var a = n.offsetParent, st = n.style;
    var abajo = a.offsetHeight - (n.offsetTop + n.offsetHeight), der = a.offsetWidth - (n.offsetLeft + n.offsetWidth);
    acomodar(function () {
      st.position = 'absolute'; st.width = n.offsetWidth + 'px';
      if (S.lado.v === 'arriba') st.top = n.offsetTop + 'px'; else st.bottom = abajo + 'px';
      if (S.lado.h === 'izq') st.left = n.offsetLeft + 'px'; else st.right = der + 'px';
      n.classList.add('saliendo', 'sale');
    });
    n._sale = function () { n._sale = null; n.classList.remove('saliendo', 'sale'); st.position = st.width = st.top = st.bottom = st.left = st.right = ''; };
    alTerminar(n, ms, function () { if (!n._sale) return; n._sale(); fin(); });
  }
  function otraVez(n) {
    if (!n._sale) return false;
    acomodar(function () { n._sale(); });
    return true;
  }
  /* una copia de lo que había, que se desvanece encima mientras cambia lo de abajo (las tarjetas) */
  function fantasma(n, dentro) {
    dentro = dentro || n.parentNode;
    if (!anima(n) || !n.firstChild || !n.cloneNode || !visible(dentro) || n.offsetParent !== dentro) return;
    var g = n.cloneNode(true);
    g.classList.remove('entra');                 /* la copia no vuelve a entrar: solo se desvanece */
    g.classList.add('wsm-fantasma');
    g.style.left = n.offsetLeft + 'px'; g.style.top = n.offsetTop + 'px'; g.style.width = n.offsetWidth + 'px';
    dentro.appendChild(g);
    var a = g.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 160, easing: 'ease-out', fill: 'forwards' });
    a.onfinish = function () { g.remove(); };
  }
  /* lo que entra dentro de la burbuja (tarjetas, «aprendió», archivos), una vez */
  function entra(n) { if (n && anima(n) && n.firstChild) { n.classList.remove('entra'); void n.offsetWidth; n.classList.add('entra'); } }

  /* ---------- armar ---------- */
  function montar(raiz) {
    R.raiz = raiz; raiz.textContent = '';
    R.globo = el('div', 'wsm-globo'); R.globo.hidden = true;
    var x = el('button', 'wsm-x'); x.title = 'Minimizar: se guarda en tu Compañero  (Esc)'; x.appendChild(icono('x')); x.onclick = function () { guardar(); };
    R.cab = el('div', 'wsm-cab'); R.tu = el('div', 'wsm-tu'); R.txt = el('div', 'wsm-txt');
    R.ext = el('div', 'wsm-ext'); R.pas = el('div', 'wsm-pasos'); R.tar = el('div'); R.uso = el('div', 'wsm-uso');
    R.sigue = el('div', 'wsm-sigue');
    /* la plática entera de esta conversación (lo de antes, lo tuyo, su respuesta y sus archivos): se recorre sola */
    R.conv = el('div', 'wsm-conv'); R.hilo = el('div', 'wsm-hilo'); R.hilo.hidden = true;
    R.fila = el('div', 'wsm-fila'); R.fila.hidden = true;  /* lo que mandaste mientras trabajaba: espera en fila */
    /* C2: lo suyo de ahora va a la izquierda, sin globo, con su carita; debajo, lo que hizo (C3) y sus archivos */
    R.dia = el('div', 'wsm-dia'); R.dia.hidden = true;
    R.ag = el('div', 'wsm-h-ag wsm-ahora'); R.ag.hidden = true;
    R.cara = el('i', 'cara'); R.cu = el('div', 'cu'); R.hizo = el('div', 'wsm-hizo-caja');
    [R.txt, R.hizo, R.ext].forEach(function (n) { R.cu.appendChild(n); });
    R.ag.appendChild(R.cara); R.ag.appendChild(R.cu);
    [R.hilo, R.dia, R.tu, R.ag, R.fila].forEach(function (n) { R.conv.appendChild(n); });
    /* C1: sin barra de scroll. La plática vive en una caja que la desvanece arriba y abajo cuando hay más, con una
       rayita de 3 pt que solo se ve mientras recorres y «↓ Lo nuevo» si llega algo mientras estás arriba */
    R.convCaja = el('div', 'wsm-conv-caja'); R.raya = el('i', 'wsm-raya');
    R.nuevo = el('button', 'wsm-nuevo', '↓ Lo nuevo'); R.nuevo.hidden = true; R.nuevo.title = 'Ir a lo último';
    R.nuevo.onclick = function () { alFinal(true); };
    [R.conv, R.raya, R.nuevo].forEach(function (n) { R.convCaja.appendChild(n); });
    R.conv.addEventListener('scroll', function () { recorrido(true); });
    R.nota = el('div', 'wsm-nota-linea'); R.nota.hidden = true;   /* lo que pasó con un enlace, en una línea que se va */
    R.lic = el('div', 'wsm-lic'); R.lic.hidden = true;     /* lo que hizo con el permiso que diste para este trabajo */
    [x, R.cab, R.convCaja, R.nota, R.tar, R.pas, R.lic, R.sigue, R.uso].forEach(function (n) { R.globo.appendChild(n); });

    R.barra = el('div', 'wsm-barra'); R.barra.hidden = true;
    R.ags = el('div', 'wsm-ags'); R.sin = el('div', 'wsm-sin', SIN_AGENTES); R.sin.hidden = true;
    R.chips = el('div', 'wsm-chips');                      /* lo que tienes enfrente (D3-a) y lo que soltaste */
    R.nomira = el('div', 'wsm-nomira'); R.nomira.hidden = true;   /* el motor no puede mirar desde el monito (aún) */
    R.pista1 = el('div', 'wsm-pista1'); R.pista1.hidden = true;
    R.version = el('div', 'wsm-version', APP_VIEJA); R.version.hidden = true;   /* la app es de antes que su burbuja */
    /* tu respuesta, cuando lo último que hizo fue una entrega: va como «Pedir cambios» a esa entrega (o solo platicas) */
    R.sobre = el('div', 'wsm-sobre'); R.sobre.hidden = true;
    var caja = el('div', 'wsm-caja');
    R.ta = el('textarea'); R.ta.rows = 1; R.ta.spellcheck = false;
    R.send = el('button', 'wsm-send'); R.send.title = 'Mandar'; R.send.appendChild(icono('up'));
    /* el sitio del micrófono (bloque V, carril 4): vacío no ocupa lugar; su pieza se monta con WSM.mic.montar(nodo) */
    R.mic = el('div', 'wsm-mic');
    caja.appendChild(R.ta); caja.appendChild(R.mic); caja.appendChild(R.send);
    R.caja = caja;
    var pie = el('div', 'wsm-pie');
    var a1 = el('span'); a1.appendChild(el('kbd', null, 'Enter')); a1.appendChild(document.createTextNode(' manda'));
    var a2 = el('span'); a2.appendChild(el('kbd', null, 'Tab')); a2.appendChild(document.createTextNode(' cambia de agente'));
    var a3 = el('span'); a3.appendChild(el('kbd', null, 'Esc')); a3.appendChild(document.createTextNode(' cierra'));
    [a1, a2, a3].forEach(function (n) { pie.appendChild(n); });
    [R.ags, R.sin, R.version, R.chips, R.pista1, R.nomira, R.sobre, caja, pie].forEach(function (n) { R.barra.appendChild(n); });

    R.nido = el('div', 'wsm-nido');
    R.yo = el('div', 'wsm-yo'); R.ray = el('i', 'ray7 r-dormido');
    R.pista = el('div', 'wsm-pista', 'Llámalo'); R.pista.appendChild(el('small', null, '⌥ Espacio'));
    [R.yo, R.ray, R.pista].forEach(function (n) { R.nido.appendChild(n); });
    prepararNido();

    [R.globo, R.barra, R.nido].forEach(function (n) { raiz.appendChild(n); });
    /* las manos (F1): su caja va entre la barra y el nido, y es parte de la burbuja (sus zonas de clic, su movimiento) */
    if (typeof WSMManos !== 'undefined') R.manos = WSMManos.montar(R);
    /* E1 · entregas (40_entregas.js): sus tarjetas, el toque, el panel grande y los botones de la barra */
    if (typeof WSMEntregas !== 'undefined') {
      WSMEntregas.montar(R);
      /* sus tarjetas (encargos) van en la plática: se recorren con ella y el encabezado nunca se va de la vista */
      var encs = WSMEntregas.piezasDentro ? WSMEntregas.piezasDentro() : null;
      if (encs && R.conv) R.conv.appendChild(encs);
    }

    R.ta.addEventListener('input', alEscribir);
    R.ta.addEventListener('keydown', function (e) {
      if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && !e.shiftKey && !e.altKey && !e.metaKey && recordar(e.key === 'ArrowUp' ? -1 : 1)) { e.preventDefault(); return; }
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); enviar(); }
      else if (e.key === 'Escape') { e.preventDefault(); if (e.stopPropagation) e.stopPropagation(); quitarChat(); }
      else if (e.key === 'Tab') { e.preventDefault(); siguiente(e.shiftKey ? -1 : 1); }
    });
    R.send.onclick = enviar;
    /* Esc con el foco en cualquier lado (no solo en la caja de escribir): lo mismo, se guarda */
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') quitarChat(); });
    prepararSoltar(raiz);
    ponerMonito(); pintarBarra(); estado('duerme');
    setInterval(zonas, 150);
    /* cómo lo dejaste (grande o chico): aquí, y la app lo confirma con lo que guardó (WSM.modo) */
    try { if (window.localStorage && localStorage.getItem(MODO) === 'grande') S.modo = 'grande'; } catch (e) { }
    /* el micrófono, si su pieza ya está cargada (carril 4 · 28_voz.js): en ESTA caja, antes de «Mandar». Es la misma
       caja en la burbuja y en el chat grande, así que se pone una vez (y ponerlo dos veces no pone dos) */
    try { if (typeof WSMVoz !== 'undefined' && WSMVoz && typeof WSMVoz.montar === 'function') WSMVoz.montar({ caja: R.caja, ta: R.ta, nido: R.nido, antes: R.send, sitio: R.mic, api: W.mic }); } catch (e) { }
    if (enVentana() && ent()) WSMEntregas.abrirGrande();        /* la ventana del chat grande: siempre en grande */
    else if (enApp()) host({ op: 'grande_estado' });
    return W;
  }
  /* esta página es la ventana del chat grande (la app la carga con esa clase): no hay nido ni burbuja chica */
  function enVentana() { return document.documentElement.classList.contains('wsm-ventana'); }

  /* ---------- la plática se recorre sin barra: desvanecido, rayita y «↓ Lo nuevo» (C1) ---------- */
  function alFondoYa() { var C = R.conv; return !C.scrollHeight || C.scrollHeight - C.scrollTop - C.clientHeight < 32; }
  /* dónde va: el desvanecido solo del lado donde hay más; la rayita, mientras recorres (y se va sola) */
  function recorrido(mueve) {
    var C = R.conv, K = R.convCaja; if (!C || !K) return;
    var resto = C.scrollHeight - C.clientHeight, arriba = C.scrollTop > 3, abajo = resto - C.scrollTop > 3;
    K.classList.toggle('mas-arriba', arriba); K.classList.toggle('mas-abajo', abajo);
    if (alFondoYa()) loNuevo(false);
    if (resto <= 3 || !C.clientHeight) { R.raya.classList.remove('ve'); return; }
    var alto = Math.max(18, Math.round(C.clientHeight * C.clientHeight / C.scrollHeight));
    R.raya.style.height = alto + 'px';
    R.raya.style.top = Math.round((C.offsetTop || 0) + (C.clientHeight - alto) * (C.scrollTop / resto)) + 'px';
    if (!mueve) return;
    R.raya.classList.add('ve');
    clearTimeout(S.relojRaya);
    S.relojRaya = setTimeout(function () { R.raya.classList.remove('ve'); }, 900);
  }
  function loNuevo(si) {
    S.nuevo = !!si;
    if (R.nuevo && R.nuevo.hidden === S.nuevo) R.nuevo.hidden = !S.nuevo;
  }
  function alFinal(suave) {
    var C = R.conv; if (!C) return;
    if (suave && C.scrollTo && !quieto()) { try { C.scrollTo({ top: C.scrollHeight, behavior: 'smooth' }); } catch (e) { C.scrollTop = C.scrollHeight; } }
    else C.scrollTop = C.scrollHeight;
    loNuevo(false);
    setTimeout(function () { recorrido(false); }, 0);
  }
  /* de qué está hecha la plática ahora (para saber si llegó algo): mensajes, lo que lleva escrito y lo que te pide */
  function firmaPlatica() {
    var a = actual(), t = S.turno;
    return [a.id, hilo(a.id).length, t ? (t.tu || '').length + ':' + (t.texto || '').length : '', (S.permiso && S.permiso.id) || '',
      (S.pregunta && S.pregunta.id) || '', S.enFila ? 1 : 0].join('|');
  }

  /* ---------- ↑ y ↓ en la caja: tus mensajes anteriores (como en una terminal) ---------- */
  function mios() {
    var a = actual(), l = hilo(a.id).filter(function (x) { return x.rol === 'yo' && x.texto; }).map(function (x) { return x.texto; });
    if (S.turno && S.turno.tu) l.push(S.turno.tu);
    return l.filter(function (t, i) { return i === 0 || t !== l[i - 1]; });
  }
  /* d: -1 (el anterior) o 1 (el siguiente). Solo con la caja vacía o ya recordando: si escribes algo tuyo, ↑↓ son
     del texto. → true si lo tomó */
  function recordar(d) {
    var r = S.rec;
    if (!r) {
      if (d > 0 || R.ta.value) return false;
      var l = mios(); if (!l.length) return false;
      r = S.rec = { l: l, i: l.length };
    }
    r.i += d;
    if (r.i >= r.l.length) { S.rec = null; R.ta.value = ''; alEscribir(true); return true; }
    if (r.i < 0) r.i = 0;
    R.ta.value = r.l[r.i]; alEscribir(true);
    return true;
  }

  /* ---------- el nido: un clic lo llama; arrastrarlo lo cambia de lugar (la app mueve la ventana) ---------- */
  function prepararNido() {
    var n = R.nido;
    n.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      if (S.vuela || afuera()) { host({ op: 'volver' }); return; }   /* su nido vacío: un clic lo trae de regreso */
      S.toque = { x: e.screenX, y: e.screenY, arrastra: false };
      if (n.setPointerCapture && e.pointerId !== undefined) { try { n.setPointerCapture(e.pointerId); } catch (x) { } }
    });
    n.addEventListener('pointermove', function (e) {
      var t = S.toque; if (!t || t.arrastra || !enApp()) return;
      if (Math.abs(e.screenX - t.x) + Math.abs(e.screenY - t.y) < UMBRAL_ARRASTRE) return;
      t.arrastra = true; arrastre(true); host({ op: 'arrastrar', fase: 'empieza' });
    });
    n.addEventListener('pointerup', function () {
      var t = S.toque; S.toque = null;
      if (!t || t.arrastra) return;                          /* soltar tras arrastrar: lo termina la app */
      llamar();
    });
    n.addEventListener('pointercancel', function () { S.toque = null; });
  }
  /* un clic en el Compañero: abierto, lo guarda todo; guardado, lo trae como lo dejaste. En la app decide la app (toma
     primero lo que tienes enfrente, como con ⌥ Espacio) */
  function llamar() {
    if (S.vuela) return;
    if (!enApp()) { if (abierto()) guardar(); else barra(true); return; }
    if (!abierto()) S.llama = setTimeout(function () { S.llama = null; barra(true); }, 260);   /* si la app no contesta */
    host({ op: 'llamar' });
  }
  /* agarrarlo (la app lo arrastra): el nido se levanta y el monito mira hacia arriba con un brinquito; lo que tiene
     abierto (burbuja, barra, tarjetas) se queda pegado y se mueve con él. Al soltarlo baja con su rebote. */
  function agarrar(si) {
    S.agarrado = !!si;
    R.raiz.classList.toggle('agarrado', S.agarrado);
    var m = MONO;
    if (m && si) { m.quieto = true; m.tgy = -3; if (!quieto()) m.salta(.5); }
    else if (m) { m.quieto = S.estado === 'escuchando'; m.tgy = 0; if (!quieto()) { m.sx = 1.12; m.sy = .88; } }
  }
  /* un clic en el nido sin moverse (lo ve la app, que lo hace de una vez): si anda volando, que regrese; si no, llamarlo */
  function clicNido() { return S.vuela || afuera() ? 'volver' : 'llamar'; }
  /* la mudanza de lado (la dirige la app, Monito.mudarse; el monito no se mueve en la pantalla): 1 → esconder el nido
     (la app puso encima una foto idéntica) y lo que tiene abierto; 2 → ya del lado nuevo: enseñarlo; 0 → se cortó:
     todo a la vista. Cada fase contesta cuando ya se pintó. */
  function mudanza(f, n) {
    function pintado(fn) { requestAnimationFrame(function () { requestAnimationFrame(fn); }); }
    if (f === 1) {
      var abierto = !quieto() && [R.globo, R.barra].some(function (x) { return x && !x.hidden; });
      R.raiz.classList.add('mudando');
      setTimeout(function () { pintado(function () { host({ op: 'mudanza', fase: 1, n: n }); }); }, abierto ? 130 : 0);
    } else if (f === 2) {
      pintado(function () {
        R.raiz.classList.remove('mudando');
        pintado(function () { host({ op: 'mudanza', fase: 2, n: n }); });
      });
    } else R.raiz.classList.remove('mudando');
  }
  /* el arrastre de antes (una app que no lo hace nativo): mientras lo arrastras, la burbuja y la barra se apartan */
  function arrastre(si) {
    S.arrastra = !!si;
    R.raiz.classList.toggle('arrastrando', S.arrastra);
    var m = MONO;
    if (m && si) { m.quieto = true; m.tgy = -3; if (!quieto()) m.salta(.5); }
    else if (m) { m.quieto = S.estado === 'escuchando'; m.tgy = 0; m.sx = 1.12; m.sy = .88; }
  }
  /* hacia dónde abre la burbuja: h «der» (el nido a la derecha, abre a la izquierda) o «izq»; v «abajo» (abre hacia
     arriba) o «arriba» (abre hacia abajo) */
  function lado(h, v) {
    S.lado = { h: h === 'izq' ? 'izq' : 'der', v: v === 'arriba' ? 'arriba' : 'abajo' };
    R.raiz.classList.toggle('izq', S.lado.h === 'izq');
    R.raiz.classList.toggle('arriba', S.lado.v === 'arriba');
    return S.lado;
  }

  function ponerMonito() {
    var a = actual(), st = MONO_DE[S.estado] || 'libre';
    R.raiz.style.setProperty('--c', a.c); R.raiz.style.setProperty('--ac', a.c); R.raiz.style.setProperty('--acx', contraste(a.c));
    R.raiz.style.setProperty('--brillo', claroHex(a.c) ? 'transparent' : 'color-mix(in srgb,' + a.c + ' 24%,transparent)');
    if (MONO && MONO.c === a.c && MONO.f === a.f) return;
    R.yo.textContent = '';
    MONO = new Monito(a.c, a.f, PX); MONO.setEstado(st); R.yo.appendChild(MONO.el);
    R.pista.firstChild.textContent = a.id ? 'Llama a ' + a.n : 'Llámalo';
  }

  /* ---------- estados ---------- */
  function estado(st) {
    if (!MONO_DE[st]) st = 'reposo';
    var antes = S.estado, m = MONO; S.estado = st;
    if (QUIETOS[st] && S.turno && S.turno.vivo) { S.turno.vivo = false; S.turno.fin = !!S.turno.texto; }
    if ((st === 'pensando' || st === 'haciendo') && S.turno && S.turno.fin) S.turno.otro = true;   /* empezó otro turno suyo */
    R.raiz.setAttribute('data-wsm', st);
    if (antes === 'escuchando' && st !== 'escuchando' && m) { m.quieto = false; m.tabre = 1; m.tgx = 0; m.tgy = 0; }
    if (m && (st !== antes || m.estado !== MONO_DE[st])) m.setEstado(MONO_DE[st]);
    if (m && st === 'escuchando' && antes !== 'escuchando') { m.quieto = true; m.tabre = 1.16; m.tgx = -1.6; m.tgy = -4.4; if (!quieto()) m.salta(.6); }
    if (m && st === 'listo' && antes !== 'listo' && !quieto()) { m.salta(1.05); m.rafaga(7); }      /* con «reducir movimiento», sin brincos */
    pintarRaya(); pintarCab(); trabajo();
    if (R.txt) R.txt.classList.toggle('vivo', vivoAhora());
  }
  /* ¿trabaja ahora? Su turno de aquí, o un encargo suyo en segundo plano. */
  function trabajando() {
    if (TRABAJA[S.estado]) return true;
    try { return ent() && !!WSMEntregas.trabajaEnFondo && WSMEntregas.trabajaEnFondo(S.elegido); } catch (e) { return false; }
  }
  /* El gesto de trabajo: mientras trabaja, además de leer con la mirada y sus puntitos (su estado «trabaja»), el
     monito da un brinquito y suelta una chispa cada pocos segundos, por el motor de su propio cuerpo (un solo dueño).
     Con «reducir movimiento», sin brincos ni chispas: quedan sus puntitos. */
  var BEAT_MS = 2200;
  function trabajo() {
    var si = trabajando();
    if (R.raiz) R.raiz.classList.toggle('trabaja', si);
    if (si && !S.latido && !quieto()) {
      S.beat = 0;
      S.latido = setInterval(function () {
        var m = MONO; if (!m || !trabajando() || quieto() || S.vuela || S.estado === 'escuchando') return;
        S.beat++;
        m.salta(.38);
        if (S.beat % 2 && m.signo) m.signo('chispa', { donde: S.beat % 4 === 1 ? 'der' : 'izq', esc: .55, sube: 10, dur: 900 });
      }, BEAT_MS);
    } else if (!si && S.latido) { clearInterval(S.latido); S.latido = null; }
  }
  /* la rayita: solo se rehace si cambió (rehacerla reiniciaba sus puntitos a cada evento) */
  function pintarRaya() {
    var k = RAYA_DE[S.estado] || 'libre', r = R.ray;
    if (S.estado === 'haciendo' && S.pasos) k = 'skill';            /* los pasos de su skill: la rayita los cuenta */
    unIndicador();
    var firma = k + (k === 'skill' ? '|' + (S.pasos ? S.pasos.n + '/' + S.pasos.i : '3/0') : '');
    if (r._k === firma) return;
    r._k = firma; r.className = 'ray7 r-' + k; r.textContent = '';
    if (k === 'pensando') for (var i = 0; i < 3; i++) r.appendChild(el('b'));
    if (k === 'skill') {
      var n = S.pasos ? S.pasos.n : 3, p = S.pasos ? S.pasos.i : 0;
      for (var j = 0; j < n; j++) r.appendChild(el('b', j < p ? 'h' : j === p ? 'a' : ''));
    }
  }
  /* los puntitos del monito se guardan cuando otro indicador habla (los pasos de la skill o el ojito) */
  function unIndicador() {
    var m = MONO; if (!m || !m.pensar || !m.pensar.style) return;
    var ojo = typeof WSMManos !== 'undefined' && WSMManos.s && WSMManos.s.ojo > 0;
    m.pensar.style.display = (S.estado === 'haciendo' && S.pasos) || ojo ? 'none' : '';
  }
  function alEscribir(recordando) {
    if (recordando !== true) S.rec = null;                 /* escribiste algo tuyo: ↑↓ vuelven a ser del texto */
    R.ta.style.height = CAJA_MIN + 'px';
    var alto = Math.max(CAJA_MIN, Math.min(CAJA_MAX, R.ta.scrollHeight || 0));
    R.ta.style.height = alto + 'px';
    R.ta.classList.toggle('tope', (R.ta.scrollHeight || 0) > CAJA_MAX);   /* más de 5 renglones: se recorre */
    pintarSend();
    var m = MONO; if (!m || S.estado !== 'escuchando') return;
    m.gel.vel += (Math.random() < .5 ? -1 : 1) * 15; m.sy = .97;
    if (Math.random() < .1) m.parpadea();
    clearTimeout(S.quieto); m.tabre = 1.16;
    S.quieto = setTimeout(function () { if (S.estado === 'escuchando') { m.tabre = 1; m.parpadea(true); } }, 1400);
  }
  function subiendo() { return S.adjuntos.some(function (x) { return !x.ruta && !x.mal; }); }
  function pintarSend() {
    var hay = !!R.ta.value.trim() || S.adjuntos.some(function (x) { return x.ruta; });
    R.send.disabled = !hay || subiendo() || !actual().id;
    R.send.title = subiendo() ? 'Espera: estoy subiendo tu archivo' : 'Mandar';
  }

  /* ---------- agentes ---------- */
  function agentes(lista, elegido) {
    S.agentes = (lista || []).map(limpio).filter(function (a) { return a.id; });
    S.conAgentes = S.agentes.length > 0;
    var e = ag(elegido) ? elegido : ag(S.elegido) ? S.elegido : (S.agentes[0] || {}).id || '';
    if (e) elegir(e, false); else { ponerMonito(); pintarBarra(); }
    if (S.estado === 'duerme' && !S.aviso) estado('reposo');
  }
  function elegir(id, avisar) {
    if (!ag(id)) return;
    var cambia = id !== S.elegido;
    S.elegido = id;
    if (cambia) {
      S.turno = null; S.pregunta = null; S.permiso = null; S.pasos = null; S.hace = ''; S.uso = ''; S.responde = null; S.sinManos = '';
      PERM = CICLO.nuevo(); S.cambios = null; S.platicar = false; S.licencia = null;
      S.rec = null; S.firma = ''; loNuevo(false); if (S.busca) buscar('');
    }
    ponerMonito(); pintarBarra(); pintarGlobo();
    if (cambia && S.grande) alFinal(false);
    if (cambia && ent() && WSMEntregas.alElegir) WSMEntregas.alElegir(id);
    if (cambia && S.estado !== 'escuchando') estado('reposo');
    else if (MONO && S.estado === 'escuchando') { MONO.quieto = true; MONO.tabre = 1.16; MONO.tgx = -1.6; MONO.tgy = -4.4; MONO.salta(.8); }
    if (avisar && cambia) host({ op: 'elegir', agente: id });
  }
  function siguiente(d) {
    if (S.agentes.length < 2) return;
    var i = S.agentes.indexOf(actual());
    elegir(S.agentes[(i + d + S.agentes.length) % S.agentes.length].id, true);
  }

  /* ---------- la barra ---------- */
  function pintarBarra() {
    var a = actual(), k = JSON.stringify([S.agentes.map(function (x) { return [x.id, x.n, x.c, x.f]; }), a.id]);
    if (R.ags._k !== k) {                                   /* los monitos de la fila, solo si cambiaron */
      R.ags._k = k; R.ags.textContent = '';
      S.agentes.forEach(function (x) {
        var b = el('button', 'wsm-ag' + (x.id === a.id ? ' on' : '')); b.style.setProperty('--c', x.c);
        b.title = x.n; b.appendChild(monito(x.c, x.f, 30, { quieto: x.id !== a.id })); b.appendChild(el('span', null, x.n));
        b.onclick = function () { elegir(x.id, true); R.ta.focus(); };
        R.ags.appendChild(b);
      });
    }
    R.ags.hidden = S.agentes.length < 2;
    R.sin.hidden = S.conAgentes !== false;                 /* sin agentes: lo dice, en vez de una caja que no manda */
    R.ta.disabled = S.conAgentes === false;
    requestAnimationFrame(function () {                      /* el elegido, a la vista (sin mover la página) */
      var on = R.ags.querySelector('.on'); if (!on) return;
      var izq = on.offsetLeft - R.ags.offsetLeft, der = izq + on.offsetWidth;
      if (der > R.ags.scrollLeft + R.ags.clientWidth) R.ags.scrollLeft = der - R.ags.clientWidth + 6;
      else if (izq < R.ags.scrollLeft) R.ags.scrollLeft = Math.max(0, izq - 6);
    });
    var sobre = S.responde ? null : entregaReciente();
    S.cambios = sobre;
    /* de entrada: «Pedir cambios» si la hizo su conversación de trabajo; si salió de esta plática, la plática sigue */
    if (sobre && sobre.ruta !== S.sobreRuta) { S.sobreRuta = sobre.ruta; S.platicar = !sobre.deEncargo; }
    R.ta.placeholder = S.conAgentes === false ? 'Sin agentes todavía' : S.responde ? 'Tu respuesta…'
      : sobre && !S.platicar ? '¿Qué le cambio a «' + sobre.nombre + '»?'
      : a.id ? (hilo(a.id).length || S.turno ? 'Contéstale a ' : 'Escríbele a ') + a.n + '…' : 'Escríbele…';
    R.nomira.textContent = S.sinManos || ''; R.nomira.hidden = !S.sinManos || !!S.responde;
    R.version.hidden = !S.appVieja;
    pintarSobre(sobre);
    pintarChips(); pintarSend();
    if (ent()) WSMEntregas.botones();
  }
  /* Los archivos que soltaste, cada uno con su ✕. Lo que tienes enfrente (la app y su ventana, D3-a) ya no se pinta:
     el chip parecía algo que había que tocar (decisión del dueño, 21-nov). Viaja callado con tu mensaje si lo dejas
     prendido en el menú del monito («Decirle a mi agente qué tengo enfrente»), y la primera vez lo dice una línea. Si el
     motor del agente no puede mirar desde el monito (S.sinManos), no viaja. */
  function pintarChips() {
    var C = R.chips, ctx = S.ctx && !S.responde && !S.sinManos ? S.ctx : null;
    var k = JSON.stringify([S.adjuntos.map(function (x) { return [x.nombre, x.ruta || '', x.mal || '']; }), actual().n]);
    pista(!!ctx);
    if (C._k === k) return;
    C._k = k;
    (function () {
      C.textContent = '';
      S.adjuntos.forEach(function (x) {
        var d = el('span', 'wsm-chip adj' + (x.mal ? ' mal' : x.ruta ? '' : ' sub'));
        d.appendChild(el('span', null, (x.mal ? 'No subió: ' : x.ruta ? '' : 'Subiendo… ') + x.nombre));
        d.title = x.mal || x.ruta || 'subiendo…';
        var q2 = el('button', 'wsm-cx'); q2.title = 'Quitar'; q2.appendChild(icono('x'));
        q2.onclick = function () { fantasma(d, R.barra); S.adjuntos.splice(S.adjuntos.indexOf(x), 1); acomodar(pintarChips); pintarSend(); };
        d.appendChild(q2); C.appendChild(d);
      });
      C.hidden = !C.firstChild;
    })();
  }
  /* La primera vez que lo de enfrente va a viajar, una línea tranquila que lo dice (una sola vez en esta Mac): que
     el agente sabe la app y la ventana, que no ve tu pantalla y dónde se apaga. */
  var PISTA = 'wsm.pista.enfrente.menu';
  function pista(viaja) {
    var P = R.pista1; if (!P) return;
    if (!viaja) { P.hidden = true; return; }
    if (S.pistaVista === undefined) {
      try { S.pistaVista = !!(window.localStorage && localStorage.getItem(PISTA) === '1'); } catch (e) { S.pistaVista = false; }
    }
    if (!P.hidden || S.pistaVista) return;          /* ya está a la vista, o ya la viste otra vez */
    P.textContent = 'Cuando me llamas, le digo a ' + (actual().n || 'tu agente') + ' qué app y qué ventana tienes enfrente '
      + '(no ve tu pantalla). Puedes apagarlo en mi menú, arriba en la barra.';
    P.hidden = false; entra(P);
    S.pistaVista = true;
    try { localStorage.setItem(PISTA, '1'); } catch (e) { }
  }
  /* `aqui`: la barra chica aunque lo hayas dejado en grande (lo que soltaste en el monito vive en ESTA burbuja) */
  function barra(abrir, aqui) {
    abrir = abrir === undefined ? !S.barra : !!abrir;
    if (S.llama) { clearTimeout(S.llama); S.llama = null; }
    /* en el chat grande la caja de escribir es parte de la ventana: ni se abre ni se cierra, solo toma el teclado */
    if (S.grande) { if (R.ta.focus) R.ta.focus(); return; }
    /* lo llamaste (un clic o ⌥ Espacio) y el grande está abierto o así lo dejaste: vuelve EN GRANDE (G3-a) */
    if (abrir && !S.barra && aqui !== true && ent() && (S.fuera || S.modo === 'grande') && !S.responde) { WSMEntregas.abrirGrande(); return; }
    if (abrir === S.barra) { if (abrir) R.ta.focus(); return; }
    S.barra = abrir;
    if (abrir) {
      S.cerrado = false;                                      /* la llamaste: lo de esta conversación se ve otra vez */
      /* volvió a abrir mientras salía: se queda, sin volver a entrar (nada de doble animación) */
      if (!otraVez(R.barra)) acomodar(function () { R.barra.hidden = false; });
      pintarBarra();
      if (actual().id && (hilo(actual().id).length || S.turno)) pintarGlobo();   /* sabes en qué hilo escribes */
      else if (!R.globo.hidden) acomodar(pintarSigue);
      /* vas a contestar: lo último de la plática, a la vista (la barra le quitó alto) */
      setTimeout(function () { if (S.barra && R.conv) R.conv.scrollTop = R.conv.scrollHeight; }, 0);
      if (ent()) host({ op: 'botones' });                     /* los de la oficina, por si los cambió */
      if (!VIVOS[S.estado] && S.estado !== 'pregunta') { S.antes = S.estado === 'duerme' ? 'reposo' : S.estado; estado('escuchando'); }
      setTimeout(function () { if (S.barra) R.ta.focus(); }, 30);
    } else {
      S.responde = null;
      if (R.ta.blur) R.ta.blur();
      salir(R.barra, 200, function () { if (!S.barra) { R.barra.hidden = true; if (R.pista1) R.pista1.hidden = true; } });
      if (S.estado === 'escuchando') estado(S.antes === 'listo' ? 'reposo' : S.antes || 'reposo');
      if (!R.globo.hidden) { if (hayAlgo()) acomodar(pintarSigue); else cerrarGlobo(false); }
    }
    host({ op: 'barra', abierta: abrir });
  }
  /* Esc en la barra: quita el chat de una vez (la barra y la respuesta se desvanecen juntas, en su lugar). Lo que te
     pide algo (una pregunta, un permiso) se queda. Antes la misma tecla llegaba dos veces (a la barra y a la página):
     la barra desaparecía, la respuesta brincaba hacia abajo y luego se iba. */
  function quitarChat() {
    /* Esc buscando en el grande: cierra la búsqueda (y si no había nada que cerrar, sigue: nunca se traga la tecla) */
    if (S.grande && S.busca && ent()) { WSMEntregas.buscarCerrar(); if (!S.busca) return; }
    if (!S.grande && (S.vuela || afuera())) host({ op: 'volver' });   /* Esc también lo trae de regreso si andaba volando */
    guardar();
  }
  /* ---------- guardar y llamar: UN modelo ----------
     El Compañero está «abierto» (chico: esta burbuja con su barra; o grande: su ventana) o «guardado» (solo él en su
     nido). GUARDAR esconde TODO y siempre es lo mismo, venga de donde venga: Esc, «×», «─ Minimizar», un clic en él,
     ⌥ Espacio o el menú de arriba (estos tres los decide la app y llegan aquí con `deApp`). Lo único que se queda es lo
     que te PIDE algo (un permiso, una pregunta). Llamarlo otra vez lo trae como estaba (S.modo). Cambiar de tamaño es
     otro control: «⤢» y «⤡ Chico». */
  function abierto() { return !!(S.barra || S.grande || S.fuera || (ent() && WSMEntregas.grandeAbierto())); }
  function guardar(deApp) {
    if (S.llama) { clearTimeout(S.llama); S.llama = null; }
    /* la ventana del chat grande: la guarda la app, con todo lo demás */
    if (enVentana()) { if (ent()) WSMEntregas.minimizar(); return; }
    /* la app esconde lo demás (su ventana grande, sus fichas) y anota cómo estaba; se le dice ANTES de cerrar aquí,
       para que sepa que estaba en chico. Si fue ella quien lo pidió, ya lo está haciendo. */
    if (!deApp && abierto() && enApp()) host({ op: 'guardar' });
    if (ent() && WSMEntregas.grandeAbierto()) WSMEntregas.minimizar();      /* el grande junto al nido (el boceto, una app de antes) */
    if (ent()) WSMEntregas.cerrarToque();                                   /* el aviso que hubiera, también */
    /* (si tu agente sigue trabajando, al guardarlo sale su «sigue trabajando · te aviso cuando termine», que se va solo) */
    if (!R.globo.hidden && !S.permiso && !S.pregunta) cerrarGlobo(true);
    barra(false);
  }
  function afuera() { return typeof WSMManos !== 'undefined' && WSMManos.fuera ? WSMManos.fuera() : false; }
  /* lo que tienes enfrente, del lado de la app (la toma al abrir la barra, antes de enseñarla): viaja con tu mensaje
     (sin pintarse); `null` si lo apagaste en el menú del monito */
  function contexto(c) {
    var ok = c && typeof c === 'object' && typeof c.app === 'string' && c.app.trim();
    var datos = {};
    if (ok) for (var k in c) { if (k !== 'icono') datos[k] = c[k]; }
    S.ctx = ok ? { app: c.app.trim().slice(0, 80), ventana: String(c.ventana || '').trim().slice(0, 120), datos: datos } : null;
    S.ctxFuera = false;
    if (ent()) WSMEntregas.frente(ok ? datos : null);         /* los botones de la barra según lo de enfrente */
    if (S.barra) acomodar(pintarChips); else pintarChips();
  }
  function conAdjuntos(t) {
    var listos = S.adjuntos.filter(function (x) { return x.ruta; });
    if (!listos.length) return t;
    return (t ? t + ' ' : '') + '(adjunté: ' + listos.map(function (x) { return x.ruta; }).join(', ') + ')';
  }
  /* ---------- la plática de esta conversación (el hilo) ---------- */
  function hilo(id) { return S.hilos[id] || []; }
  /* lo que llega de la página: toda la conversación del monito con ese agente (lo último al final) */
  function alHistorial(ev) {
    var id = String(ev.agente || ''); if (!id) return;
    var lista = (ev.turnos || []).filter(function (x) { return x && (x.rol === 'yo' || x.rol === 'agente' || x.rol === 'nota'); })
      .map(function (x) { return { rol: x.rol, texto: String(x.texto || ''), archivos: x.archivos || null, t: +x.t || 0,
        herr: Array.isArray(x.herr) && x.herr.length ? x.herr.slice(0, 60) : null }; });
    /* el turno de ahora (si hay) no se repite: su parte ya escrita en la página se quita del final */
    var t = id === S.elegido ? S.turno : null;
    if (t && t.tu) {
      for (var i = lista.length - 1; i >= 0; i--) {
        if (lista[i].rol === 'yo' && lista[i].texto.indexOf(t.tu) >= 0) { lista = lista.slice(0, i); break; }
      }
    }
    S.hilos[id] = lista;
    if (id === S.elegido && !R.globo.hidden) acomodar(pintarDentro);
    if (id === S.elegido && S.pideHilo) { S.pideHilo = false; pintarGlobo(); if (S.grande) alFinal(false); }
  }
  /* el turno que se ve pasa al hilo (antes de empezar otro o al cerrar la burbuja): nada de la plática se pierde */
  function archivarTurno() {
    var t = S.turno, a = actual(); if (!t || !a.id) return;
    var h = S.hilos[a.id] = hilo(a.id).slice();
    if (t.tu) h.push({ rol: 'yo', texto: t.tu, t: t.t0 || 0 });
    if (t.texto || (t.archivos && t.archivos.length)) h.push({ rol: 'agente', texto: t.texto || '', archivos: t.archivos || null,
      t: t.t1 || t.t0 || 0, herr: t.herr || null });
    if (h.length > 200) h.splice(0, h.length - 200);
    S.turno = null;
  }
  /* La entrega de la que hablan ahora: la de su última respuesta (si dejó un archivo). Tu respuesta va como «Pedir
     cambios» a esa entrega (la hace su conversación de trabajo, en la misma tarjeta), salvo que elijas «Solo platicar». */
  function entregaReciente() {
    if (!ent() || !actual().id) return null;
    var arch = WSMEntregas.entregaVisible ? WSMEntregas.entregaVisible(actual().id) : null;   /* un encargo a la vista */
    if (arch) {}
    else if (S.turno) {
      if (!S.turno.fin || S.turno.vivo) return null;
      var pr = WSM_TEXTO.preparar(S.turno.texto || '', S.turno.archivos);
      arch = pr.archivos[pr.archivos.length - 1] || null;
    } else {
      var h = hilo(actual().id);
      for (var i = h.length - 1; i >= Math.max(0, h.length - 4) && !arch; i--) {
        if (h[i].nota) break;                               /* ya le pediste cambios: lo siguiente es platicar */
        if (h[i].rol !== 'agente') continue;
        var p2 = WSM_TEXTO.preparar(h[i].texto || '', h[i].archivos); arch = p2.archivos[p2.archivos.length - 1] || null;
      }
    }
    if (!arch || !arch.ruta) return null;
    return { ruta: arch.ruta, titulo: arch.titulo || '', nombre: arch.ruta.split(/[\\/]/).pop() || arch.ruta,
      deEncargo: !!(WSMEntregas.deEncargo && WSMEntregas.deEncargo(actual().id, arch.ruta)) };
  }
  function pintarSobre(sobre) {
    var P = R.sobre, k = sobre ? sobre.ruta + '|' + !!S.platicar : '';
    if (P._k === k) return;
    P._k = k; P.textContent = ''; P.hidden = !sobre;
    if (!sobre) return;
    P.appendChild(el('span', null, 'Sobre «' + (sobre.titulo || sobre.nombre) + '»:'));
    var c1 = el('button', 'chip' + (S.platicar ? '' : ' p on'), 'Pedir cambios'), c2 = el('button', 'chip' + (S.platicar ? ' p on' : ''), 'Solo platicar');
    c1.title = 'Tu mensaje va a su conversación de trabajo y sale la versión nueva en la misma tarjeta';
    c2.title = 'Tu mensaje sigue esta plática, sin tocar la entrega';
    c1.onclick = function () { S.platicar = false; acomodar(pintarBarra); R.ta.focus(); };
    c2.onclick = function () { S.platicar = true; acomodar(pintarBarra); R.ta.focus(); };
    P.appendChild(c1); P.appendChild(c2);
  }
  /* lo que viaja con tu mensaje: el texto y, si lo dejas, lo que tenías enfrente */
  function opMandar(a, t) {
    var op = { op: 'mandar', agente: a.id, texto: t };
    if (R.pista1) R.pista1.hidden = true;
    if (S.ctx && !S.sinManos) op.contexto = S.ctx.datos;
    else if (S.ctxFuera || S.sinManos) op.sin_contexto = true;   /* lo quitaste (o su motor no puede): no viaja */
    return op;
  }
  /* ¿su motor sigue trabajando en lo de antes? (lo que mandes ahora espera su turno en la página) */
  function ocupado() { return !!(TRABAJA[S.estado] && S.turno && !S.turno.fin); }
  function enviar() {
    var t = R.ta.value.trim(), a = actual();
    if ((!t && !S.adjuntos.some(function (x) { return x.ruta; })) || !a.id || subiendo()) return;
    t = conAdjuntos(t);
    var leyo = null;
    /* tu respuesta a una entrega: «Pedir cambios» (la versión nueva en su tarjeta, de su conversación de trabajo) */
    if (!S.responde && S.cambios && !S.platicar && ent() && WSMEntregas.pedirCambioDe &&
        WSMEntregas.pedirCambioDe(a.id, S.cambios.ruta, t)) {
      var nom = S.cambios.titulo || S.cambios.nombre;
      archivarTurno();
      hilo(a.id).push({ rol: 'yo', texto: t, nota: 'Pediste cambios a «' + nom + '»', t: ahoraMs() / 1000 });
      S.turno = null; S.cambios = null; S.adjuntos = []; S.verHilo = true; S.cerrado = false; R.ta.value = ''; alEscribir(); barra(false);
      if (ent()) WSMEntregas.seguirCambio(a.id);
      pintarGlobo();
      return;
    }
    /* mientras trabaja en lo de antes, lo tuyo espera en fila: se dice, y lo que estaba haciendo no se borra */
    if (!S.responde && ocupado()) {
      host(opMandar(a, t));
      S.enFila = { tu: t }; S.cerrado = false;
      S.ctx = null; S.ctxFuera = false; S.adjuntos = []; R.ta.value = ''; alEscribir(); barra(false); pintarGlobo();
      return;
    }
    if (S.turno) archivarTurno();
    if (S.enFila) S.enFila = null;
    S.sobreRuta = '';
    if (S.responde) host({ op: 'responder', agente: a.id, id: S.responde, texto: t });
    else {
      if (S.ctx && !S.sinManos && S.ctx.datos && S.ctx.datos.seleccion) leyo = { app: S.ctx.app, seleccion: true };
      host(opMandar(a, t));
    }
    /* lo que leyó antes en SU conversación sigue en su cabeza: la marca es por agente y no se borra al mandar otro
       mensaje (Fable v2 §1.4); solo la quita la app (WSM.olvido) */
    S.leidos = S.leidos || {};
    if (leyo) S.leidos[a.id] = { app: leyo.app };
    S.leido = S.leidos[a.id] || null; S.turno = { tu: t, texto: '', vivo: true, extra: null, t0: ahoraMs() / 1000 }; S.pregunta = null; S.permiso = null; S.pasos = null; S.aviso = null; S.hace = '';
    S.ctx = null; S.ctxFuera = false; S.adjuntos = []; S.cerrado = false; S.licencia = null;
    R.ta.value = ''; alEscribir(); barra(false); estado('pensando'); pintarGlobo();
  }
  /* la app avisa que el agente leyó tu pantalla o contenido ajeno en SU conversación (leer_ventana, ver_pantalla, lo
     que tienes enfrente con tu selección o un archivo): la tarjeta de permiso lo dice con una marca chiquita, y la marca
     dura toda su conversación (por agente) */
  function leyo(info) {
    var a = String((info && info.agente) || actual().id || '');
    S.leidos = S.leidos || {};
    var antes = S.leidos[a] || (a === actual().id ? S.leido : null);
    S.leidos[a] = { app: String((info && info.app) || (antes && antes.app) || '').slice(0, 80), ajeno: !!((info && info.ajeno) || (antes && antes.ajeno)) };
    if (a === actual().id) S.leido = S.leidos[a];
    if (S.permiso && !R.globo.hidden) acomodar(pintarTarjeta);
  }
  /* el socio borró la marca (menú del monito) o empezó otra conversación con ese agente */
  function olvido(info) {
    var a = String((info && info.agente) || actual().id || '');
    if (S.leidos) delete S.leidos[a];
    if (a === actual().id) S.leido = null;
    if (S.permiso && !R.globo.hidden) acomodar(pintarTarjeta);
  }

  /* ---------- soltar un archivo en el monito: a su cerebro, como el clip de la página ---------- */
  function prepararSoltar(raiz) {
    function hayArchivos(e) { return e.dataTransfer && [].indexOf.call(e.dataTransfer.types || [], 'Files') >= 0; }
    raiz.addEventListener('dragover', function (e) { if (hayArchivos(e)) { e.preventDefault(); if (e.dataTransfer) { try { e.dataTransfer.dropEffect = 'copy'; } catch (x) { } } raiz.classList.add('soltar'); } });
    raiz.addEventListener('dragleave', function (e) { if (!raiz.contains(e.relatedTarget)) raiz.classList.remove('soltar'); });
    raiz.addEventListener('drop', function (e) {
      raiz.classList.remove('soltar');
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
      e.preventDefault(); adjuntar(e.dataTransfer.files);
    });
  }
  function adjuntar(files) {
    var a = actual(); if (!a.id) return;
    barra(true, !S.grande);
    [].slice.call(files || []).forEach(function (f) {
      var x = { nombre: String(f.name || 'archivo') }; S.adjuntos.push(x);
      if (f.size > MAX_ADJUNTO) { x.mal = 'pasa de 20 MB'; acomodar(pintarChips); return; }
      var rd = new FileReader();
      rd.onload = function () { host({ op: 'adjuntar', agente: a.id, nombre: x.nombre, datos: String(rd.result).split(',')[1] || '' }); };
      rd.onerror = function () { x.mal = 'no lo pude leer'; acomodar(pintarChips); };
      rd.readAsDataURL(f);
    });
    acomodar(pintarChips); pintarSend();
  }
  function adjunto(ev) {
    var x = S.adjuntos.filter(function (y) { return y.nombre === ev.nombre && !y.ruta && !y.mal; })[0];
    if (!x) return;
    if (ev.ruta) x.ruta = ev.ruta; else x.mal = ev.mal || 'no se pudo';
    acomodar(pintarChips); pintarSend();
    if (ent()) { WSMEntregas.botones(); WSMEntregas.alAdjunto(ev); }
  }

  /* ---------- la burbuja ---------- */
  function vivoAhora() { return !!(S.turno && S.turno.vivo && S.turno.texto && !S.aviso); }
  /* el encabezado: con quién y en qué conversación estás («Luna · esta conversación»), su estado y «Seguir en la
     página». Solo se rehace si cambió (rehacerlo a cada trozo reiniciaba el brillo de «pensando») */
  function pintarCab() {
    var a = actual(), t = S.aviso ? '' : TXT[S.estado], k = [a.n, a.id, t, !!VIVOS[S.estado]].join('|');
    if (S.grande && ent() && WSMEntregas.estadoGrande) WSMEntregas.estadoGrande(t === 'te escucha' ? '' : t, !!VIVOS[S.estado]);
    if (R.cab._k === k) return;
    R.cab._k = k; R.cab.textContent = '';
    R.cab.appendChild(el('i', 'pt')); R.cab.appendChild(el('b', null, a.n || 'Workspace'));
    if (a.id) R.cab.appendChild(el('span', 'conv', '· esta conversación'));
    if (t) { var e = el('i', 'estado'); e.appendChild(el('span', null, t)); if (!VIVOS[S.estado]) e.firstChild.style.animation = 'none'; R.cab.appendChild(e); }
    if (a.id) {
      R.cab.appendChild(el('i', 'br'));                   /* «Seguir en la página», en su propio renglón chiquito */
      var b = el('button', 'wsm-ir wsm-ir-cab', 'Seguir en la página'); b.appendChild(icono('der'));
      b.title = 'Abre la página de Workspace en ' + a.n + ' con lo que hablaron aquí';
      b.onclick = function () { b.disabled = true; host({ op: 'seguir', agente: a.id }); };
      R.cab.appendChild(b);
    }
  }
  /* ¿hay algo que enseñar? Con la barra abierta, también la plática de antes (así sabes en qué hilo escribes) */
  function hayAlgo() {
    var a = actual();
    return !!(S.grande || S.turno || S.pregunta || S.permiso || PERM.listo || S.aviso || S.pasos || S.enFila || (ent() && WSMEntregas.hay())
      || ((S.barra || S.verHilo) && a.id && hilo(a.id).length));
  }
  function pintarGlobo() {
    /* el chat grande está abierto en su ventana: lo nuevo se ve ALLÁ (esta burbuja no brinca ni lo cierra) */
    if (S.fuera) return;
    /* el chat grande aquí mismo: la plática es parte de él, siempre a la vista; lo nuevo aparece adentro (G-1) */
    if (S.grande) { R.globo.hidden = false; pintarDentro(); return; }
    if (!hayAlgo()) { cerrarGlobo(false); return; }
    /* la cerraste mientras trabajaba: no se vuelve a abrir sola (te toca al terminar); lo que te pide algo, sí */
    if (R.globo.hidden && S.cerrado && !(S.permiso || S.pregunta || (S.aviso && S.aviso.grave))) return;
    /* entra una vez (su clase, al dejar de estar escondida); si estaba saliendo, se queda (vuelve a su lugar) */
    if (!otraVez(R.globo)) acomodar(function () { R.globo.hidden = false; pintarDentro(); });
    else acomodar(pintarDentro);
  }
  function pintarDentro() {
    R.globo.classList.toggle('mal', !!(S.aviso && S.aviso.grave));
    pintarCab();
    var C = R.conv, abajo = alFondoYa(), firma = firmaPlatica(), a0 = actual();
    var llego = !!S.firma && S.firma !== firma && S.firma.split('|')[0] === a0.id;
    S.firma = firma;
    pintarHilo();
    var tu = S.turno && S.turno.tu; R.tu.hidden = !tu; if (R.tu.textContent !== (tu || '')) R.tu.textContent = tu ? tu : '';
    /* el separador del día, antes de lo de ahora (si lo anterior fue otro día, o es lo primero de la plática) */
    var conDia = !!(S.turno && S.turno.t0 && R.hilo._dia !== 'Hoy' && WSM_PLATICA.dia(S.turno.t0, ahoraMs() / 1000) === 'Hoy');
    if (R.dia.hidden === conDia) { R.dia.hidden = !conDia; if (conDia) R.dia.textContent = 'Hoy'; }
    var pr = null, cuerpo = '';
    if (S.aviso) cuerpo = S.aviso.texto;
    else { pr = S.turno ? WSM_TEXTO.preparar(S.turno.texto, S.turno.archivos) : null; cuerpo = pr ? pr.cuerpo : ''; }
    if (R.txt._k !== cuerpo) { R.txt._k = cuerpo; md(R.txt, cuerpo); }
    R.txt.classList.toggle('vivo', vivoAhora());
    /* su carita, solo junto a lo que dijo (un aviso de Workspace va sin carita) */
    var ck = a0.c + '|' + a0.f;
    if (R.cara._k !== ck) { R.cara._k = ck; R.cara.textContent = ''; try { R.cara.appendChild(monito(a0.c, a0.f, 20, { quieto: true })); } catch (e) { } }
    R.ag.hidden = !(cuerpo || (pr && (pr.archivos.length || pr.aprendio.length)));
    R.ag.classList.toggle('aviso', !!S.aviso);
    pintarHizo();
    pintarExtras(S.aviso ? null : pr); pintarFila(); pintarPasos(); pintarTarjeta(); pintarLic(); pintarSigue();
    if (ent()) WSMEntregas.pintar();
    if (R.uso.textContent !== (S.uso || '')) R.uso.textContent = S.uso || '';
    if (abajo) { C.scrollTop = C.scrollHeight; loNuevo(false); }
    else if (llego) loNuevo(true);                           /* estabas arriba y llegó algo: «↓ Lo nuevo» */
    recorrido(false);
  }
  /* C3 · lo que hizo en este turno, en UNA línea gris que se abre (no mezclado con lo que dijo) */
  function pintarHizo() {
    var h = S.turno && !S.aviso && S.turno.fin ? S.turno.herr : null, k = h ? JSON.stringify(h) : '';
    if (R.hizo._k === k) return;
    R.hizo._k = k; R.hizo.textContent = '';
    var n = h ? WSM_PLATICA.hizo(h) : null;
    if (n) R.hizo.appendChild(n);
  }
  /* la hora de un mensaje: solo al pasar el ratón (C3) */
  /* (en un atributo, no en un hijo: el texto del mensaje queda limpio para copiarlo o buscarlo) */
  function ponerHora(n, t) { var h = t ? WSM_PLATICA.hora(t) : ''; if (h) n.setAttribute('data-hora', h); }
  function caraDe(a) { var c = el('i', 'cara'); try { c.appendChild(monito(a.c, a.f, 20, { quieto: true })); } catch (e) { } return c; }
  /* La plática de antes en esta conversación, arriba de lo de ahora (se recorre). La última respuesta con archivo trae
     su tarjeta de entrega entera; las de antes, el nombre del archivo (un clic lo abre). */
  function pintarHilo() {
    var tope = S.grande ? HILO_GRANDE : HILO_MAX, ahora = ahoraMs() / 1000, q = (S.busca || '').toLowerCase();
    var H = R.hilo, a = actual(), h = a.id ? hilo(a.id) : [], ver = h.slice(-tope), u = h[h.length - 1];
    var k = [a.id, h.length, u ? (u.texto || '').length : 0, !!S.turno, tope, q, WSM_PLATICA.dia(ahora, ahora) + new Date(ahora * 1000).getDate()].join('|');
    /* la entrega más reciente (sin un turno a la vista) trae su tarjeta entera: ahí se ve su «Haciendo la v2» */
    var conCarta = -1;
    if (!S.turno) for (var j = ver.length - 1; j >= 0; j--) if (ver[j].rol === 'agente' && (ver[j].archivos || /📄/.test(ver[j].texto || ''))) { conCarta = j; break; }
    if (H._k === k) return;
    H._k = k; H.textContent = ''; H._dia = ''; S.hallados = [];
    if (!ver.length) { H.hidden = true; return; }
    if (h.length > ver.length) {
      var mas = el('button', 'wsm-h-mas', 'Antes: ' + (h.length - ver.length) + ' mensajes más · verlos en la página');
      mas.onclick = function () { host({ op: 'ver_pagina', agente: a.id }); };
      H.appendChild(mas);
    }
    ver.forEach(function (x, i) {
      var ultimo = i === conCarta;
      /* «Hoy», «Ayer»…: un separador cada vez que cambia el día */
      var dd = x.t ? WSM_PLATICA.dia(x.t, ahora) : '';
      if (dd && dd !== H._dia) H.appendChild(el('div', 'wsm-dia', dd));
      if (dd) H._dia = dd;
      if (x.rol === 'nota') { H.appendChild(el('div', 'wsm-h-nota', x.texto)); return; }
      var n;
      if (x.rol === 'yo') {
        n = el('div', 'wsm-h-yo'); if (x.nota) n.appendChild(el('small', null, x.nota));
        n.appendChild(el('span', null, x.texto));
      } else {
        var pr = WSM_TEXTO.preparar(x.texto || '', x.archivos), cu = el('div', 'cu');
        n = el('div', 'wsm-h-ag'); n.appendChild(caraDe(a));
        if (pr.cuerpo) { var p = el('div', 'tx'); md(p, pr.cuerpo); cu.appendChild(p); }
        var hz = WSM_PLATICA.hizo(x.herr); if (hz) cu.appendChild(hz);
        pr.archivos.forEach(function (f) { cu.appendChild(ultimo && ent() ? WSMEntregas.tarjeta(f, a.id) : chipArchivo(f, a.id)); });
        n.appendChild(cu);
      }
      ponerHora(n, x.t);
      if (q && String(x.texto || '').toLowerCase().indexOf(q) >= 0) { n.classList.add('halla'); S.hallados.push(n); }
      H.appendChild(n);
    });
    H.hidden = false;
  }
  /* ---------- buscar en la plática (el chat grande): marca los mensajes que lo dicen y salta entre ellos ---------- */
  function buscar(q) {
    S.busca = String(q || '').trim().slice(0, 80);
    R.hilo._k = ''; pintarHilo();
    S.hallaI = S.hallados.length ? S.hallados.length - 1 : -1;
    return irHallado(0);
  }
  function irHallado(d) {
    var l = S.hallados || [], n = l.length;
    if (!n) return { n: 0, i: 0 };
    S.hallaI = ((S.hallaI + d) % n + n) % n;
    l.forEach(function (x, i) { x.classList.toggle('ahi', i === S.hallaI); });
    var x = l[S.hallaI];
    try { if (x.scrollIntoView) x.scrollIntoView({ block: 'center', behavior: quieto() ? 'auto' : 'smooth' }); } catch (e) { }
    return { n: n, i: S.hallaI + 1 };
  }
  /* «Copiar todo»: la plática entera de este agente, en texto (por el host: la app la pone en tu portapapeles) */
  function copiarTodo() {
    var a = actual(), l = hilo(a.id).slice();
    if (S.turno) { if (S.turno.tu) l.push({ rol: 'yo', texto: S.turno.tu }); if (S.turno.texto) l.push({ rol: 'agente', texto: WSM_TEXTO.preparar(S.turno.texto).cuerpo }); }
    l = l.map(function (x) { return x.rol === 'agente' ? { rol: x.rol, texto: WSM_TEXTO.preparar(x.texto || '').cuerpo } : x; });
    var t = WSM_PLATICA.todo(l, a.n);
    if (t) host({ op: 'copiar_texto', texto: t });
    return t;
  }
  function chipArchivo(f, agente) {
    var nom = f.ruta.split(/[\\/]/).pop() || f.ruta, b = el('button', 'wsm-h-arch');
    b.appendChild(icono('doc')); b.appendChild(el('span', null, f.titulo || nom)); b.title = 'Abrir ' + nom;
    b.onclick = function () { host({ op: ent() ? 'entrega_abrir' : 'abrir', agente: agente, ruta: f.ruta, modo: 'abrir' }); };
    return b;
  }
  /* lo que mandaste mientras trabajaba en lo de antes: espera en fila (lo dice, para que sepas que llegó) */
  function pintarFila() {
    var F = R.fila, f = S.enFila, k = f ? f.tu : '';
    if (F._k === k) return;
    var era = F.hidden;
    if (!f && !F.hidden && F.firstChild && !R.globo.hidden) fantasma(F, R.conv);   /* se va desvaneciéndose, no de golpe */
    F._k = k; F.textContent = ''; F.hidden = !f;
    if (!f) return;
    var y = el('div', 'wsm-h-yo'); y.appendChild(el('small', null, 'En fila')); y.appendChild(el('span', null, f.tu)); F.appendChild(y);
    F.appendChild(el('small', 'wsm-fila-nota', EN_FILA));
    if (era) entra(F);
  }
  /* lo que se esconde del texto vuelve como piezas: el chip «aprendió» y las tarjetas de archivo (por el puente) */
  function pintarExtras(pr) {
    var E = R.ext, a = actual(), k = pr ? JSON.stringify([pr.aprendio, pr.archivos, S.turno && S.turno.vivo]) : '';
    if (E._k === k) return;
    var habia = !!E.firstChild;
    E._k = k; E.textContent = '';
    if (!pr) { E.hidden = true; return; }
    if (pr.aprendio.length && !(S.turno && S.turno.vivo)) {
      var n = pr.aprendio[pr.aprendio.length - 1], c = el('div', 'wsm-aprendio');
      c.appendChild(icono('skill')); c.appendChild(el('span', null, n.tipo === 'skill-nueva' ? 'Aprendió algo nuevo' : 'Mejoró una skill'));
      if (n.nombre) c.appendChild(el('small', null, n.nombre));
      c.title = n.texto; E.appendChild(c);
    }
    pr.archivos.forEach(function (x) {
      if (ent()) { E.appendChild(WSMEntregas.tarjeta(x, a.id)); return; }   /* E1: la tarjeta de entrega */
      var ruta = x.ruta, nombre = ruta.split(/[\\/]/).pop() || ruta;
      var carpeta = ruta.slice(0, ruta.length - nombre.length).replace(/[\\/]$/, '').split(/[\\/]/).slice(-2).join('/');
      var w = el('div', 'wsm-arch'); w.appendChild(icono('doc'));
      var tx = el('div', 'tx'); tx.appendChild(el('b', null, x.titulo || nombre));
      tx.appendChild(el('small', null, x.titulo ? nombre + (carpeta ? ' · ' + carpeta : '') : carpeta)); tx.title = ruta; w.appendChild(tx);
      var bs = el('div', 'chips'), b1 = el('button', 'chip p', 'Abrir'), b2 = el('button', 'chip', 'Mostrar en Finder');
      b1.onclick = function () { host({ op: 'abrir', agente: a.id, ruta: ruta, modo: 'abrir' }); };
      b2.onclick = function () { host({ op: 'abrir', agente: a.id, ruta: ruta, modo: 'revelar' }); };
      bs.appendChild(b1); bs.appendChild(b2); w.appendChild(bs); E.appendChild(w);
    });
    E.hidden = !E.firstChild;
    if (!habia && !R.globo.hidden) entra(E);
  }
  /* Cuando ya contestó: [Responder] (sigue esta misma conversación) y [Copiar] lo que dijo. «Seguir en la página»
     vive en el encabezado. */
  function pintarSigue() {
    var a = actual();
    /* también cuando lo que se ve es la plática (sin turno a la vista: lo que contestó junto con lo de la fila, o una
       entrega a la que le pediste cambios): seguir es siempre un clic */
    var soloHilo = !S.turno && a.id && hilo(a.id).length > 0 && !TRABAJA[S.estado];
    var P = R.sigue, ver = !!(((S.turno && !S.turno.vivo && (S.turno.texto || S.turno.fin)) || soloHilo) && a.id && !S.aviso
      && !S.permiso && !S.pregunta);
    var k = ver ? [a.id, !!S.barra, !!(S.turno && S.turno.texto)].join('|') : '';
    if (P._k === k) return;
    var era = P.hidden || !P.firstChild;
    if (!era && !R.globo.hidden) fantasma(P);                   /* lo de antes se desvanece en su lugar */
    P._k = k; P.textContent = '';
    if (ver) {
      if (!S.barra) {
        var r = el('button', 'wsm-ir wsm-responder', 'Responder'); r.appendChild(icono('der'));
        r.title = 'Sigue esta misma conversación con ' + a.n;
        r.onclick = function () { barra(true); };
        P.appendChild(r);
      }
      /* E1: [Copiar] lo que contestó (el texto limpio, sin el 🧠 ni el menú de archivo) */
      var cp = el('button', 'wsm-ir wsm-copiar', 'Copiar');
      cp.onclick = function () { var pr = WSM_TEXTO.preparar((S.turno && S.turno.texto) || ''); host({ op: 'copiar_texto', texto: pr.cuerpo }); };
      if (S.turno && S.turno.texto) P.appendChild(cp);
    }
    P.hidden = !P.firstChild;
    if (!P.hidden && era) entra(P);
  }
  /* lo que está haciendo, en una línea y en palabras de todos los días («Haciendo: leyendo «README.md»»), con sus
     pasos si los cuenta (reportar_avance) */
  function pintarPasos() {
    var hace = S.hace && TRABAJA[S.estado] && !(ent() && WSMEntregas.hay()) ? S.hace : '';
    var P = R.pas, k = (S.pasos ? JSON.stringify(S.pasos) : '') + '|' + hace;
    if (P._k === k) return;
    if (k === '|' && !P.hidden && P.firstChild && !R.globo.hidden) fantasma(P);   /* se va desvaneciéndose, no de golpe */
    P._k = k; P.textContent = '';
    if (S.pasos) {
      var b = el('div', 'barras');
      for (var j = 0; j < S.pasos.n; j++) b.appendChild(el('b', j < S.pasos.i ? 'h' : j === S.pasos.i ? 'a' : ''));
      P.appendChild(b);
      P.appendChild(el('small', null, 'Paso ' + Math.min(S.pasos.i + 1, S.pasos.n) + ' de ' + S.pasos.n + (S.pasos.texto ? ' · ' + S.pasos.texto : '')));
    }
    if (hace) P.appendChild(el('small', 'hace', 'Haciendo: ' + hace.charAt(0).toLowerCase() + hace.slice(1)));
    P.hidden = !P.firstChild;
  }
  /* lo que hizo solo con el permiso que diste para este trabajo (una línea; se va al terminar su turno) */
  function pintarLic() {
    var L = R.lic, l = S.licencia, k = l ? [l.texto, l.usadas, l.ultima].join('|') : '';
    if (L._k === k) return;
    var era = L.hidden;
    if (!l && !L.hidden && L.firstChild && !R.globo.hidden) fantasma(L);
    L._k = k; L.textContent = ''; L.hidden = !l;
    if (!l) return;
    L.appendChild(el('b', null, 'Con tu permiso: ' + l.texto));
    if (l.ultima) L.appendChild(el('small', null, l.ultima + (l.usadas > 1 ? ' · ' + l.usadas + ' en este trabajo' : '')));
    if (era) entra(L);
  }
  /* La tarjeta de lo que te pide (un permiso de su motor o una pregunta), o la línea corta de tu respuesta. Un pedido,
     una tarjeta: tu clic la quita al momento (CICLO) y la línea «Listo…» se va sola. */
  function pintarTarjeta() {
    var q = S.permiso || S.pregunta, L = PERM.listo;
    var cual = q ? (S.permiso ? 'p|' : 'q|') + (q.id || 'terminal') : L ? 'l|' + L.texto + '|' + L.hasta : '';
    var k = cual + '|' + (q ? !!(S.leido || q.leyo) : '');
    if (R.tar._k === k) return;
    var otra = R.tar._cual !== cual;                               /* otra tarjeta (no la misma) */
    var cruza = otra && R.tar._k && R.tar.firstChild;
    if (cruza) fantasma(R.tar);                                     /* la de antes se desvanece en su lugar */
    R.tar._k = k; R.tar._cual = cual; R.tar.textContent = ''; R.tar.className = '';
    if (!q && !L) return;
    /* la nueva entra cuando la de antes ya casi se fue (sus letras nunca se enciman) */
    var entrar = otra ? function (n) { if (cruza) n.classList.add('tras'); entra(n); } : function () { };
    var a = actual();
    if (!q) {
      R.tar.className = 'wsm-listo ' + L.tipo;
      R.tar.appendChild(el('i', 'ok')); R.tar.appendChild(el('span', null, L.texto));
      entrar(R.tar);
      return;
    }
    if (S.permiso) {
      WSMPermiso.pintar(R.tar, S.permiso, { agente: a, leido: S.leido, host: host, decidir: decidir });
      entrar(R.tar);
      return;
    }
    var p = S.pregunta; R.tar.className = 'wsm-tarjeta';
    R.tar.appendChild(el('small', null, p.en_terminal ? 'Te pregunta en su terminal' : 'Te pregunta'));
    R.tar.appendChild(el('p', null, p.texto));
    var c2 = el('div', 'chips');
    if (p.en_terminal) {
      var tt = el('button', 'chip p', 'Ir a la terminal'); tt.onclick = function () { host({ op: 'terminal', agente: a.id }); }; c2.appendChild(tt);
    } else if ((p.opciones || []).length) p.opciones.forEach(function (o, i) {
      var b = el('button', 'chip' + (i === 0 ? ' p' : ''), o);
      b.onclick = function () { responder(p, o); };
      c2.appendChild(b);
    });
    else { var r = el('button', 'chip p', 'Contestar'); r.onclick = function () { S.responde = p.id; barra(true); pintarBarra(); }; c2.appendChild(r); }
    R.tar.appendChild(c2);
    entrar(R.tar);
  }
  /* tu clic: la tarjeta se va YA (no se queda «contestada» a la vista) y queda «Listo…» un momento */
  function decidir(pm, d) {
    if (!CICLO.decide(PERM, pm.id, d, ahoraMs())) return;
    host({ op: 'permiso', agente: S.elegido, id: pm.id, decision: d });
    S.permiso = null;
    var L = PERM.listo;
    setTimeout(function () { irseListo(L); }, 1650);
    if (d !== 'negar') estado('haciendo'); else estado('pensando');
    pintarGlobo();
  }
  /* la línea «Listo…» se desvanece EN SU LUGAR (nada se mueve) y luego deja su hueco (lo de abajo se acomoda) */
  function irseListo(L) {
    if (PERM.listo !== L) return;
    if (R.tar.className.indexOf('wsm-listo') < 0 || R.globo.hidden || !anima(R.tar)) { if (CICLO.tic(PERM, ahoraMs())) pintarGlobo(); return; }
    var a = R.tar.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 180, easing: 'ease-out', fill: 'forwards' });
    setTimeout(function () {
      if (PERM.listo !== L || !CICLO.tic(PERM, ahoraMs())) { a.cancel(); return; }
      acomodar(function () { a.cancel(); R.tar._k = ''; R.tar._cual = ''; R.tar.textContent = ''; R.tar.className = ''; });
      pintarGlobo();
    }, 190);
  }
  function responder(p, texto) {
    host({ op: 'responder', agente: S.elegido, id: p.id, texto: texto });
    archivarTurno();
    S.pregunta = null; S.cerrado = false; S.turno = { tu: texto, texto: '', vivo: true }; estado('pensando'); pintarGlobo();
  }
  /* «Sigo trabajando, te aviso»: la cerraste mientras trabajaba (un globito tranquilo junto al nido, sin brinco) */
  function avisarQueSigue() {
    var a = actual(); if (!ent() || !a.id) return;
    WSMEntregas.toque({ clave: 'sigue:' + a.id, agente: a.id, tipo: 'aviso', titulo: a.n + ' sigue trabajando',
      sub: 'Te aviso cuando termine.', ms: 4500 });
  }
  /* terminó mientras la tenías cerrada: el toque de siempre (brinco, globito y [Ver]); la respuesta te espera */
  function avisarQueTermino() {
    var a = actual(); if (!ent() || !a.id) return;
    var pr = WSM_TEXTO.preparar((S.turno && S.turno.texto) || '', S.turno && S.turno.archivos);
    var arch = pr.archivos[pr.archivos.length - 1];
    var sub = arch ? (arch.ruta.split(/[\\/]/).pop() || '') : WSM_PLATICA.plano(pr.cuerpo || '').trim().split('\n')[0].slice(0, 70);
    WSMEntregas.toque({ clave: 'listo:' + a.id, agente: a.id, tipo: 'termino', titulo: a.n + ' terminó', sub: sub,
      chips: [['Ver', function () { WSMEntregas.cerrarToque(); S.cerrado = false; pintarGlobo(); }, true]] });
  }
  function cerrarGlobo(manual) {
    if (S.grande) {                                          /* en el chat grande la plática no se cierra: se limpia el aviso */
      if (manual) { if (S.turno && S.turno.fin) archivarTurno(); S.aviso = null; S.pasos = null; pintarDentro(); }
      return;
    }
    if (R.globo.hidden) return;
    if (manual) {
      S.verHilo = false;
      var seguia = trabajando() && !!S.turno && !S.turno.fin;
      /* un encargo suyo (o un «Pedir cambios») en segundo plano: también te avisa al terminar (el toque del encargo) */
      var fondo = !seguia && ent() && WSMEntregas.trabajaEnFondo && WSMEntregas.trabajaEnFondo(actual().id);
      if (S.turno && S.turno.fin) archivarTurno();            /* lo que ya contestó pasa al hilo: no se pierde */
      S.aviso = null; S.pasos = null; S.enFila = S.enFila && seguia ? S.enFila : null;
      if (seguia) S.cerrado = true;
      if (seguia || fondo) avisarQueSigue();
    }
    if (manual && ent()) WSMEntregas.alCerrar();
    if (manual && (S.permiso || S.pregunta)) { pintarGlobo(); return; }      // lo que te pide no se esconde
    if (R.globo._sale) return;                                                 // ya está saliendo: no otra vez
    /* sale en su lugar (deja su hueco y se desvanece ahí): si la barra sale a la vez, nada brinca */
    salir(R.globo, 260, function () { R.globo.hidden = true; });
    if (manual && (S.estado === 'listo' || S.estado === 'error')) estado('reposo');
  }

  /* De regreso al nido: el estado que llegó durante el vuelo (si llegó alguno) o el de antes de volar. */
  function aterrizar(antes) {
    S.vuela = false;
    var ev = S.alVolver; S.alVolver = null;
    if (ev) recibir(ev); else estado(antes === 'senalando' ? 'reposo' : antes);
  }

  /* ---------- señalar (el boceto): vuela a algo de la página, lo ilumina y regresa. En la app vuela en su capa. ---------- */
  function senalar(rect, etiqueta, ms) {
    var m = MONO, cont = R.raiz.offsetParent || document.body;
    if (!m || S.vuela) return Promise.resolve();
    S.vuela = true; var antes = S.estado; estado('senalando');
    var a = R.yo.getBoundingClientRect(), c = cont.getBoundingClientRect(), a0 = actual();
    var derecha = rect.right + a.width + 12 < c.right;
    var x = derecha ? rect.right + 10 : rect.left - a.width - 10, y = rect.top + rect.height / 2 - a.height * .62;
    var dx = x - a.left, dy = y - a.top;
    m.quieto = true; m.tgx = dx < 0 ? -5 : 5; m.tgy = dy < 0 ? -3.5 : 3; m.salta(1);
    R.nido.classList.add('vacio');
    var dur = quieto() ? 1 : 950;
    var ida = R.yo.animate([{ transform: 'translate(0,0)' }, { transform: 'translate(' + dx * .5 + 'px,' + (dy * .5 - 70) + 'px) rotate(' + (dx < 0 ? -8 : 8) + 'deg)', offset: .5 },
      { transform: 'translate(' + dx + 'px,' + dy + 'px)' }], { duration: dur, easing: 'cubic-bezier(.45,0,.25,1)', fill: 'forwards' });
    return new Promise(function (fin) {
      ida.onfinish = function () {
        m.sx = 1.16; m.sy = .84; m.tgx = derecha ? -6 : 6; m.tgy = 0; m.modoOjo = 'feliz';
        var an = el('div', 'wsm-anillo'), et = el('div', 'wsm-etq', etiqueta || '');
        [an, et].forEach(function (n) { n.style.setProperty('--c', a0.c); n.style.setProperty('--acx', contraste(a0.c)); });
        an.style.left = (rect.left - c.left - 5) + 'px'; an.style.top = (rect.top - c.top - 5) + 'px';
        an.style.width = (rect.width + 10) + 'px'; an.style.height = (rect.height + 10) + 'px';
        et.style.left = (rect.left - c.left) + 'px'; et.style.top = (rect.bottom - c.top + 12) + 'px';
        cont.appendChild(an); if (etiqueta) cont.appendChild(et);
        setTimeout(function () { m.modoOjo = 'normal'; m.signo('exclama', { donde: derecha ? 'izq' : 'der', esc: .8, sube: 8 }); }, 500);
        setTimeout(function () {
          an.classList.add('sale'); et.classList.add('sale'); setTimeout(function () { an.remove(); et.remove(); }, 220);
          m.tgx = dx < 0 ? 5 : -5; m.salta(.8);
          var vuelta = R.yo.animate([{ transform: 'translate(' + dx + 'px,' + dy + 'px)' }, { transform: 'translate(' + dx * .5 + 'px,' + (dy * .5 - 50) + 'px)', offset: .5 },
            { transform: 'translate(0,0)' }], { duration: quieto() ? 1 : 780, easing: 'cubic-bezier(.45,0,.25,1)', fill: 'forwards' });
          vuelta.onfinish = function () {
            ida.cancel(); vuelta.cancel(); R.nido.classList.remove('vacio');
            m.quieto = false; m.tgx = 0; m.tgy = 0; m.sx = 1.14; m.sy = .86;
            aterrizar(antes); fin();
          };
        }, ms || 2200);
      };
    });
  }

  /* ---------- lo que llega de Workspace ---------- */
  function recibir(ev) {
    if (typeof ev === 'string') { try { ev = JSON.parse(ev); } catch (e) { return; } }
    if (!ev || !ev.t) return;
    if (ev.t === 'agentes') { agentes(ev.agentes, ev.elegido); return; }
    if (ev.t === 'barra') { barra(ev.abrir); return; }
    if (ev.t === 'contexto') { contexto(ev.contexto); return; }
    if (ev.t === 'enlace') { notaLinea(ev.texto, !ev.ok); return; }   /* lo que pasó con tu clic en «Abrir» */
    if (ev.t === 'historial') alHistorial(ev);                 /* la plática de esta conversación (y el panel grande) */
    if (ent() && WSMEntregas.recibir(ev)) return;              /* E1: entregas y encargos (de cualquier agente) */
    if (ev.t === 'historial') return;
    if (ev.t === 'hecho') { if (ent()) WSMEntregas.hecho(ev); return; }   /* lo que pasó con tu clic (abrir, revelar…) */
    if (ev.t === 'aviso') { S.aviso = ev.texto ? { texto: ev.texto, grave: !!ev.grave } : null; if (ev.texto && ev.grave) estado(ev.duerme ? 'duerme' : 'error'); pintarGlobo(); return; }
    if (ev.agente && ev.agente !== S.elegido) return;
    if (ev.t === 'estado') {
      /* mientras vuela a señalar no se mueve, pero lo último que llegó se aplica al regresar: si el turno terminaba
         en pleno vuelo, el monito volvía a «trabajando» y se quedaba así (el puente no repite un estado igual) */
      if (S.vuela) { S.alVolver = ev; return; }
      if (S.estado === 'escuchando' && ev.estado === 'reposo') return;
      S.hace = ev.hace || '';
      if (ev.estado !== 'haciendo' && !ev.pasos) S.pasos = null;
      estado(ev.estado); pintarGlobo();
    } else if (ev.t === 'parcial') {
      if (S.turno && S.turno.fin) {                         /* su turno ya terminó: un trozo tarde no prende el ▮ */
        if (!S.turno.otro) return;
        S.turno = { tu: '', texto: '', vivo: true };        /* …salvo que haya empezado otro turno suyo */
      }
      S.turno = S.turno || { tu: '' }; S.turno.texto = ev.texto || ''; S.turno.vivo = true; S.aviso = null; pintarGlobo();
    } else if (ev.t === 'respuesta') {
      var fila = S.enFila;
      S.turno = S.turno || { tu: '' }; S.turno.texto = ev.texto || ''; S.turno.archivos = ev.archivos || null;
      S.turno.herr = Array.isArray(ev.herr) && ev.herr.length ? ev.herr.slice(0, 60) : null; S.turno.t1 = ahoraMs() / 1000;
      S.turno.vivo = false; S.turno.fin = true; S.aviso = null; S.enFila = null; S.licencia = null;
      /* contestó también lo que mandaste en fila: la plática se vuelve a leer de la página, en su orden */
      if (fila) { S.turno.tu = ''; archivarTurno(); S.verHilo = true; host({ op: 'historial', agente: S.elegido }); }
      if (R.globo.hidden && S.cerrado && !S.fuera) avisarQueTermino();
      pintarGlobo();
    } else if (ev.t === 'fin') {
      if (S.turno) { S.turno.vivo = false; S.turno.fin = true; } S.licencia = null; pintarGlobo();
    } else if (ev.t === 'pregunta') {
      S.pregunta = ev.id || ev.en_terminal ? ev : null; pintarGlobo();
    } else if (ev.t === 'permiso') {
      var r = CICLO.llega(PERM, ev, ahoraMs());
      S.permiso = PERM.cual;
      if (r === 'fue') { var L = PERM.listo; setTimeout(function () { irseListo(L); }, 1850); }
      if (r !== 'igual' || !R.globo.hidden) pintarGlobo();
    } else if (ev.t === 'licencia') {
      S.licencia = ev.texto ? { texto: String(ev.texto), usadas: +ev.usadas || 0, ultima: String(ev.ultima || '') } : null;
      if (!R.globo.hidden) acomodar(pintarLic);
    } else if (ev.t === 'uso') {
      S.uso = ev.linea || ''; if (!R.globo.hidden) acomodar(function () { R.uso.textContent = S.uso; }); else R.uso.textContent = S.uso;
    } else if (ev.t === 'pasos') {
      S.pasos = ev.n ? { i: ev.i || 0, n: ev.n, texto: ev.texto || '' } : null;
      if (S.pasos) estado('haciendo'); else pintarRaya(); pintarGlobo();
    } else if (ev.t === 'adjunto') {
      adjunto(ev);
    } else if (ev.t === 'manos') {
      /* su motor no puede mirar tu pantalla desde el monito (todavía): una línea en la barra, y tu pantalla no viaja */
      S.sinManos = ev.sin ? String(ev.texto || '') : '';
      if (S.barra) acomodar(pintarBarra); else pintarBarra();
    } else if (ev.t === 'seguido') {
      var a = actual();
      S.turno = null;
      S.aviso = { texto: ev.abierta ? 'Listo: te abrí la página en ' + a.n + '. Ahí sigue la plática, con lo de aquí.'
        : 'Listo: ' + a.n + ' ya tiene lo de aquí en la página de Workspace. Ábrela y sigue ahí.' };
      pintarGlobo();
      setTimeout(function () { if (S.aviso && !S.aviso.grave) cerrarGlobo(true); }, 4500);
    }
  }

  /* ---------- para la app: dónde se puede hacer clic (lo demás deja pasar el mouse a la app de abajo) ---------- */
  function zonas() {
    if (!enApp() || enVentana()) return;
    var piezas = [R.nido, R.yo, R.globo, R.barra].concat(typeof WSMManos !== 'undefined' ? WSMManos.piezas() : [])
      .concat(ent() ? WSMEntregas.piezas() : []);
    if (ent()) WSMEntregas.zonas();                              /* dónde se toma una entrega para arrastrarla */
    var z = piezas.filter(function (n) { return n && !n.hidden && n.offsetParent; }).map(function (n) {
      var r = n.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
    });
    var k = JSON.stringify(z); if (k === ZONAS) return; ZONAS = k;
    host({ op: 'zonas', zonas: z });
  }
  /* el cursor de la Mac, en coordenadas de esta página: el monito lo sigue con los ojos como en el navegador */
  function raton(x, y) { RATON.x = x; RATON.y = y; RATON.t = performance.now() / 1000; }
  /* E1: decir algo como si lo escribieras (un botón de la barra, «Mejor aquí, corto») */
  function decir(t) {
    if (!t || !actual().id) return;
    R.ta.value = t; alEscribir(); enviar();
  }
  /* para probar la app sin teclado (MonitoEscritorio --probar): lo mismo que elegir, escribir y Enter */
  function probar(agente, texto) {
    if (agente) elegir(agente, true);
    barra(true);
    setTimeout(function () { R.ta.value = texto; alEscribir(); enviar(); }, 600);
  }

  /* una línea que dice lo que pasó y se va sola (un enlace que se abrió, o que solo se copió) */
  function notaLinea(t, mal) {
    var N = R.nota; if (!N) return;
    clearTimeout(S.relojNota);
    N.textContent = String(t || ''); N.hidden = !t; N.classList.toggle('mal', !!mal);
    if (t) { entra(N); S.relojNota = setTimeout(function () { N.hidden = true; N.textContent = ''; }, 6000); }
  }

  /* ---------- el chat grande: las MISMAS piezas (la plática y la caja de escribir), acomodadas en grande ----------
     `centro` es donde van (lo arma 27_entregas.js: la tira de agentes a un lado y «Te esperan» al otro). Al salir,
     vuelven a su lugar junto al nido. No hay un segundo chat: es este, más grande. */
  function grande(si, centro) {
    si = !!si;
    if (si === S.grande) return;
    [R.globo, R.barra].forEach(function (n) {
      if (n._sale) n._sale();
      if (n._flip) { n._flip.cancel(); n._flip = null; }
      if (n._alto) { n._alto.cancel(); n._alto = null; n.classList.remove('midiendo'); }
    });
    S.grande = si;
    R.raiz.classList.toggle('grande', si);
    R.hilo._k = '';                                          /* otro tamaño: cabe más (o menos) plática */
    if (si) {
      if (centro) { centro.appendChild(R.globo); centro.appendChild(R.barra); }
      S.barra = true; S.cerrado = false; S.verHilo = true; S.responde = null;
      R.globo.hidden = false; R.barra.hidden = false;
      if (S.estado === 'escuchando') estado(S.antes === 'listo' ? 'reposo' : S.antes || 'reposo');
      pintarBarra(); pintarDentro(); alFinal(false);
      setTimeout(function () { if (S.grande && R.ta.focus) R.ta.focus(); }, 30);
    } else {
      if (S.busca) buscar('');
      var antes = R.manos && R.manos.parentNode === R.raiz ? R.manos : R.nido;
      if (R.raiz.insertBefore) { R.raiz.insertBefore(R.barra, antes); R.raiz.insertBefore(R.globo, R.barra); }
      else { R.raiz.appendChild(R.globo); R.raiz.appendChild(R.barra); }
      S.barra = false; R.globo.hidden = true; R.barra.hidden = true; S.verHilo = false;
      if (R.ta.blur) R.ta.blur();
      /* lo que te pide algo (un permiso, una pregunta) no se esconde con el grande: se queda en la burbuja */
      if (S.permiso || S.pregunta) pintarGlobo();
    }
  }
  /* el chat grande está abierto en SU ventana (la app, G-2): esta burbuja se guarda y se calla; al cerrarse aquella
     (`si` false), `como` dice cómo quedó: 'chico' → sigue aquí, con la barra; 'grande' → minimizado (nada se abre) */
  function fuera(si, como) {
    si = !!si;
    if (como === 'grande' || como === 'chico') modo(como);
    if (si === S.fuera) return;
    if (si) {
      if (S.turno && S.turno.fin) archivarTurno();
      if (S.barra) barra(false);
      if (!R.globo.hidden) { if (R.globo._sale) R.globo._sale(); R.globo.hidden = true; }
      S.fuera = true;
      if (ent()) WSMEntregas.cerrarToque();
    } else {
      S.fuera = false; S.turno = S.turno && !S.turno.fin ? S.turno : null;
      /* lo que platicaron allá: se vuelve a leer (esta burbuja no lo vio) */
      if (actual().id) { S.pideHilo = como === 'chico'; S.verHilo = como === 'chico'; host({ op: 'historial', agente: actual().id }); }
      if (S.permiso || S.pregunta) pintarGlobo();          /* lo que te pide algo, a la vista aquí */
    }
  }
  /* cómo lo dejaste: 'grande' o 'chico' (lo guarda la app; aquí, por si la app es de antes) */
  function modo(m) {
    if (m !== 'grande' && m !== 'chico') return S.modo;
    S.modo = m;
    try { if (window.localStorage) localStorage.setItem(MODO, m); } catch (e) { }
    return S.modo;
  }
  /* ---------- el micrófono (bloque V): su sitio en la caja de escribir ----------
     La pieza de la voz (carril 4 · WSMVoz) llega suelta y se pone sola en esta caja (WSMVoz.montar({caja, ta, nido,
     antes}), que aquí se llama al montar). Para cualquier otra pieza: WSM.mic.montar(suNodo) la pone en el sitio
     (.wsm-mic, entre el texto y «Mandar»), y lo que dicte entra a la caja con WSM.mic.escribir(texto): se agrega donde
     va el cursor (o reemplaza lo provisional que ella misma puso antes, con {provisional: true}) y la caja crece sola. */
  var MIC = {
    sitio: function () { return R.mic || null; },
    montar: function (n) { if (!R.mic || !n) return null; R.mic.textContent = ''; R.mic.appendChild(n); return MIC; },
    quitar: function () { if (R.mic) R.mic.textContent = ''; },
    escribir: function (t, o) {
      t = String(t || ''); o = o || {};
      var v = R.ta.value, p = S.dictado;
      if (p && v.slice(p.i, p.i + p.n) === p.t) v = v.slice(0, p.i) + v.slice(p.i + p.n);   /* quita lo provisional de antes */
      else p = null;
      var i = p ? p.i : (typeof R.ta.selectionStart === 'number' && R.ta.selectionStart <= v.length ? R.ta.selectionStart : v.length);
      var sep = i > 0 && !/\s$/.test(v.slice(0, i)) && t ? ' ' : '', puesto = sep + t;
      R.ta.value = v.slice(0, i) + puesto + v.slice(i);
      S.dictado = o.provisional ? { i: i, n: puesto.length, t: puesto } : null;
      try { R.ta.selectionStart = R.ta.selectionEnd = i + puesto.length; } catch (e) { }
      alEscribir();
      return R.ta.value;
    },
    texto: function () { return R.ta.value; },
    enfocar: function () { if (R.ta.focus) R.ta.focus(); },
    mandar: function () { enviar(); }
  };

  /* la app de la Mac dice su versión al arrancar (si no lo dice, es de antes: se avisa en la barra) */
  function app(info) {
    S.app = info && typeof info === 'object' ? info : null;
    S.appVieja = !S.app || (+S.app.version || 0) < CONTRATO;
    if (R.version) R.version.hidden = !S.appVieja;
    return S.appVieja;
  }
  var W = { montar: montar, recibir: recibir, barra: barra, estado: estado, elegir: elegir, agentes: agentes, app: app,
    CONTRATO: CONTRATO, ciclo: CICLO, hilo: hilo,
    contexto: contexto, adjuntar: adjuntar, senalar: senalar, raton: raton, probar: probar, lado: lado,
    arrastre: arrastre, agarrar: agarrar, clicNido: clicNido, mudanza: mudanza, leyo: leyo, olvido: olvido, acomodar: function (fn) { acomodar(fn); }, salir: salir, quieto: quieto, host: host,
    unIndicador: unIndicador, aterrizar: aterrizar, decir: decir, pintarGlobo: pintarGlobo, cerrarGlobo: cerrarGlobo,
    grande: grande, fuera: fuera, modo: modo, guardar: guardar, abierto: abierto, mic: MIC, buscar: buscar, irHallado: irHallado, copiarTodo: copiarTodo,
    recordar: recordar, alFinal: alFinal, enVentana: enVentana, RENGLONES: RENGLONES, CAJA_MAX: CAJA_MAX, adjuntarEn: adjuntar,
    piezas: function () { return R; }, mono: function () { return MONO; }, s: S, alHost: null };
  return W;
})();
