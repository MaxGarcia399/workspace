/* ================= señalar: el monito vuela por tu pantalla (F1, «manos») =================
   Una capa transparente por pantalla: la app de la Mac (MonitoEscritorio) la pone encima de todo, en todos los
   escritorios, y deja pasar los clics. El monito es el MISMO de la página y de la esquina (Monito, de
   web/front/src/10_monitos.js), con la forma y el color del agente: sale del nido, vuela en arco hasta lo que te
   enseña, lo ilumina con un anillo suave y sus esquinas pixel, dice qué es en una etiqueta y regresa. Nunca hace clic
   ni escribe: solo enseña.
   Idea de Clicky y OpenClicky (MIT, ver escritorio/mac/NOTICE.md): el vuelo en arco con el cuerpo que se estira y
   la etiqueta junto al objetivo. Aquí con el lenguaje del sitio: lo que se mueve va con resorte suave y lo pixel
   (estela, esquinas, salida) va en escalón.

   La app manda tramos (uno por pantalla) con WSS.tramo({c, f, desde, pasos, hasta}) en coordenadas de ESTA pantalla
   (puntos, arriba-izquierda); la capa contesta por webkit.messageHandlers.capa: {op:'listo'}, {op:'paso', n} al llegar
   a cada paso y {op:'fin'} al terminar el tramo. */
var WSS = (function () {
  var PX = 76;
  var R = {}, M = null, VIVO = 0;
  var QUIETO = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W = { alHost: null };

  function host(op) {
    if (W.alHost) { try { W.alHost(op); } catch (e) { } return; }
    try { window.webkit.messageHandlers.capa.postMessage(op); } catch (e) { }
  }
  function nodo(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
  function vivo(tk) { return tk === VIVO; }
  function dormir(ms) { return new Promise(function (ok) { setTimeout(ok, ms); }); }
  function acotar(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function contraste(c) { try { return claro(c) ? '#151518' : '#ffffff'; } catch (e) { return '#151518'; } }

  /* cubic-bezier(x1,y1,x2,y2) como función de 0…1 (la misma curva que en CSS) */
  function curvaCSS(x1, y1, x2, y2) {
    function b(t, p1, p2) { var u = 1 - t; return 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t; }
    function db(t, p1, p2) { var u = 1 - t; return 3 * u * u * p1 + 6 * u * t * (p2 - p1) + 3 * t * t * (1 - p2); }
    return function (x) {
      if (x <= 0) return 0; if (x >= 1) return 1;
      var t = x;
      for (var i = 0; i < 8; i++) { var d = db(t, x1, x2); if (Math.abs(d) < 1e-5) break; t -= (b(t, x1, x2) - x) / d; t = acotar(t, 0, 1); }
      return b(t, y1, y2);
    };
  }
  var VUELO = curvaCSS(.45, 0, .25, 1);       /* despega con calma y llega suave */

  /* ---------- armar ---------- */
  function montar() {
    R.raiz = document.getElementById('wss') || document.body;
    R.yo = nodo('div', 'wss-yo'); R.yo.hidden = true;
    R.cuerpo = nodo('div', 'wss-cuerpo'); R.yo.appendChild(R.cuerpo);
    R.raiz.appendChild(R.yo);
    host({ op: 'listo' });
  }
  function quien(c, f) {
    c = /^#[0-9a-fA-F]{6}$/.test(c || '') ? c.toLowerCase() : '#ffffff';
    if (!M || M.c !== c || M.f !== f) {
      R.cuerpo.textContent = '';
      M = new Monito(c, FORMAS6.indexOf(f) >= 0 ? f : 'bolita', PX);
      M.setEstado('libre'); M.quieto = true;
      R.cuerpo.appendChild(M.el);
    }
    R.raiz.style.setProperty('--c', c); R.raiz.style.setProperty('--acx', contraste(c));
    R.mw = PX; R.mh = PX * 133 / 118;
  }
  function poner(p) { R.pos = { x: p.x, y: p.y }; R.yo.style.transform = 'translate(' + p.x.toFixed(1) + 'px,' + p.y.toFixed(1) + 'px)'; }
  function cuerpo(rot, sx, sy) { R.cuerpo.style.transform = 'rotate(' + rot.toFixed(2) + 'deg) scale(' + sx.toFixed(3) + ',' + sy.toFixed(3) + ')'; }
  function mirar(dx, dy) { if (!M) return; var d = Math.hypot(dx, dy) || 1; M.tgx = dx / d * 6; M.tgy = dy / d * 4.4; }

  /* dónde se para el monito junto a lo que enseña: a la derecha si cabe, si no a la izquierda, si no encima */
  function junto(t) {
    var w = innerWidth, h = innerHeight, gap = 12, der = t.x + t.w + gap + R.mw <= w - 6;
    var x = der ? t.x + t.w + gap : t.x - gap - R.mw, y = t.y + t.h / 2 - R.mh * .6;
    if (!der && x < 6) { x = acotar(t.x + t.w / 2 - R.mw / 2, 6, w - R.mw - 6); y = t.y - R.mh - gap; if (y < 6) y = t.y + t.h + gap; der = false; }
    return { x: acotar(x, 6, w - R.mw - 6), y: acotar(y, 6, h - R.mh - 6), der: der };
  }

  /* ---------- el vuelo: arco con el cuerpo que se estira, estela pixel y aterrizaje con resorte ---------- */
  function volar(b, tk) {
    var a = R.pos, dx = b.x - a.x, dy = b.y - a.y, dist = Math.hypot(dx, dy);
    if (QUIETO || dist < 2) { poner(b); return Promise.resolve(vivo(tk)); }
    var dur = acotar(420 + dist * .5, 560, 1250);
    /* el punto de control: hacia arriba de la línea (perpendicular), más alto si el viaje es largo */
    var nx = -dy / (dist || 1), ny = dx / (dist || 1); if (ny > 0) { nx = -nx; ny = -ny; }
    var alto = acotar(dist * .24, 46, 170), cx = (a.x + b.x) / 2 + nx * alto, cy = (a.y + b.y) / 2 + ny * alto;
    mirar(dx, dy); M.salta(.5);
    var agacha = R.cuerpo.animate([{ transform: 'scale(1,1)' }, { transform: 'scale(1.14,.84)' }], { duration: 130, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'forwards' });
    return new Promise(function (fin) {
      agacha.onfinish = function () {
        agacha.cancel();
        var t0 = performance.now(), cuadro = 0, antes = { x: a.x, y: a.y };
        function paso(ahora) {
          if (!vivo(tk)) { fin(false); return; }
          var lin = acotar((ahora - t0) / dur, 0, 1), p = VUELO(lin), u = 1 - p;
          var x = u * u * a.x + 2 * u * p * cx + p * p * b.x, y = u * u * a.y + 2 * u * p * cy + p * p * b.y;
          var vx = x - antes.x; antes = { x: x, y: y };
          poner({ x: x, y: y });
          var estira = Math.sin(Math.PI * lin);
          cuerpo(acotar(vx * 1.6, -13, 13), 1 - .08 * estira, 1 + .13 * estira);
          if (++cuadro % 3 === 0 && lin < .92) estela(x + R.mw / 2, y + R.mh * .78);
          if (lin < 1) requestAnimationFrame(paso);
          else {
            cuerpo(0, 1, 1);
            R.cuerpo.animate([{ transform: 'scale(1.2,.8)' }, { transform: 'scale(.95,1.06)', offset: .45 }, { transform: 'scale(1,1)' }],
              { duration: 440, easing: 'cubic-bezier(.2,.8,.2,1)' });
            M.gel.vel += (dx < 0 ? -1 : 1) * 55;
            fin(true);
          }
        }
        requestAnimationFrame(paso);
      };
    });
  }
  function estela(x, y) {
    var q = nodo('i', 'wss-px'), s = 4 + Math.round(Math.random() * 3);
    q.style.left = (x - s / 2 + (Math.random() - .5) * 10).toFixed(0) + 'px'; q.style.top = (y - s / 2 + (Math.random() - .5) * 6).toFixed(0) + 'px';
    q.style.width = q.style.height = s + 'px';
    q.addEventListener('animationend', function () { q.remove(); });
    R.raiz.appendChild(q);
  }
  /* un «puf» pixel: cuadritos que salen en escalón (al entrar o salir por otra pantalla) */
  function puf(x, y) {
    if (QUIETO) return;
    for (var i = 0; i < 10; i++) {
      var q = nodo('i', 'wss-puf'), a = i / 10 * Math.PI * 2 + Math.random() * .4, d = 26 + Math.random() * 18;
      q.style.left = x + 'px'; q.style.top = y + 'px';
      q.style.setProperty('--dx', (Math.cos(a) * d).toFixed(0) + 'px'); q.style.setProperty('--dy', (Math.sin(a) * d).toFixed(0) + 'px');
      q.addEventListener('animationend', function (e) { e.target.remove(); });
      R.raiz.appendChild(q);
    }
  }
  function aparecer(p, tk) {
    poner(p); R.yo.hidden = false; puf(p.x + R.mw / 2, p.y + R.mh * .6);
    if (QUIETO) return dormir(60).then(function () { return vivo(tk); });
    var an = R.cuerpo.animate([{ transform: 'scale(0)', opacity: 0 }, { transform: 'scale(1.08)', opacity: 1, offset: .6 }, { transform: 'scale(1)', opacity: 1 }],
      { duration: 420, easing: 'cubic-bezier(.2,.9,.25,1.15)' });
    return new Promise(function (ok) { an.onfinish = function () { ok(vivo(tk)); }; });
  }
  function desaparecer(tk) {
    puf(R.pos.x + R.mw / 2, R.pos.y + R.mh * .6);
    if (QUIETO) { R.yo.hidden = true; return dormir(60).then(function () { return vivo(tk); }); }
    var an = R.cuerpo.animate([{ transform: 'scale(1.1,.86)' }, { transform: 'scale(0)', opacity: 0 }], { duration: 260, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' });
    return new Promise(function (ok) { an.onfinish = function () { R.yo.hidden = true; an.cancel(); ok(vivo(tk)); }; });
  }

  /* ---------- lo que enseña: anillo suave, esquinas pixel y la etiqueta que se escribe sola ---------- */
  /* la etiqueta va pegada a lo que enseña, sin tapar al monito ni salirse de la pantalla: abajo o arriba, alineada a
     la izquierda o a la derecha del anillo; si nada cabe, debajo del monito */
  function dondeEtiqueta(r, ew, eh, mon) {
    var sep = 12, W = innerWidth, H = innerHeight;
    var cand = [[r.x, r.y + r.h + sep], [r.x + r.w - ew, r.y + r.h + sep], [r.x, r.y - eh - sep], [r.x + r.w - ew, r.y - eh - sep]];
    if (mon) cand.push([mon.x + R.mw / 2 - ew / 2, mon.y + R.mh + 6], [mon.x + R.mw / 2 - ew / 2, mon.y - eh - 6]);
    function choca(x, y) { return mon && x < mon.x + R.mw + 4 && x + ew > mon.x - 4 && y < mon.y + R.mh + 4 && y + eh > mon.y - 4; }
    for (var i = 0; i < cand.length; i++) {
      var c = cand[i];
      if (c[0] >= 8 && c[1] >= 8 && c[0] + ew <= W - 8 && c[1] + eh <= H - 8 && !choca(c[0], c[1])) return { x: c[0], y: c[1] };
    }
    return { x: acotar(r.x, 8, W - ew - 8), y: acotar(r.y + r.h + sep, 8, H - eh - 8) };
  }
  function iluminar(t, etiqueta, n, de, mon) {
    var g = [], pad = t.punto ? 0 : 6, an = nodo('div', 'wss-anillo' + (t.punto ? ' punto' : ''));
    var x = t.x - pad, y = t.y - pad, w = t.w + pad * 2, h = t.h + pad * 2;
    /* un punto suelto (sin elemento ni texto): «por aquí», más amplio y punteado, sin prometer precisión */
    if (t.punto) { w = h = 76; x = t.x + t.w / 2 - 38; y = t.y + t.h / 2 - 38; }
    an.style.left = x + 'px'; an.style.top = y + 'px'; an.style.width = w + 'px'; an.style.height = h + 'px';
    ['a', 'b', 'c', 'd'].forEach(function (k) { an.appendChild(nodo('i', 'wss-esq ' + k)); });
    R.raiz.appendChild(an); g.push(an);
    if (etiqueta || de > 1) {
      var et = nodo('div', 'wss-etq');
      if (de > 1) { var nn = nodo('b', 'n'); for (var i = 1; i <= de; i++) nn.appendChild(nodo('i', i < n ? 'h' : i === n ? 'a' : '')); et.appendChild(nn); }
      var tx = nodo('span', 't'); et.appendChild(tx);
      var cur = nodo('i', 'cur'); et.appendChild(cur);
      R.raiz.appendChild(et); g.push(et);
      /* se mide con el texto completo y luego se escribe: así no brinca. Una frase larga baja de renglón (nunca se
         corta); su tamaño queda fijo desde el principio */
      tx.textContent = etiqueta || '';
      if (et.scrollWidth > et.clientWidth + 1 || (etiqueta || '').length > 38) et.classList.add('larga');
      var ew = et.offsetWidth, eh = et.offsetHeight; tx.textContent = '';
      var lugar = dondeEtiqueta({ x: x, y: y, w: w, h: h }, ew, eh, mon);
      et.style.left = lugar.x + 'px'; et.style.top = lugar.y + 'px';
      et.style.minWidth = ew + 'px'; et.style.minHeight = eh + 'px';
      g.escrita = escribir(tx, cur, etiqueta || '');
    }
    return g;
  }
  /* se escribe sola a ~22 ms por letra, POR TIEMPO (cuántas letras van según el reloj, en cada cuadro): si la página se
     frena un momento, se pone al día en vez de quedarse a medias. → cuánto tarda en estar entera (ms) */
  function escribir(tx, cur, s) {
    if (QUIETO || !s) { tx.textContent = s; cur.remove(); return 0; }
    var tk = VIVO, t0 = performance.now(), dura = s.length * 22;
    (function letra() {
      if (!vivo(tk) || !tx.isConnected) return;
      var n = Math.min(s.length, Math.ceil((performance.now() - t0) / 22));
      if (tx.textContent.length !== n) tx.textContent = s.slice(0, n);
      if (n < s.length) requestAnimationFrame(letra);
      else setTimeout(function () { cur.classList.add('fin'); }, 650);
    })();
    setTimeout(function () { if (vivo(tk) && tx.isConnected && tx.textContent !== s) tx.textContent = s; }, dura + 120);
    return dura;
  }
  function apagar(g) {
    g.forEach(function (n) { n.classList.add('sale'); setTimeout(function () { n.remove(); }, 300); });
  }

  /* ---------- un tramo: los pasos de esta pantalla ---------- */
  async function tramo(T) {
    var tk = ++VIVO;
    limpiar(false);
    quien(T.c, T.f);
    var pasos = T.pasos || [];
    if (T.desde) { poner(T.desde); R.yo.hidden = false; }
    else if (pasos.length) { if (!(await aparecer(junto(pasos[0]), tk))) return; }
    else if (T.hasta) { if (!(await aparecer(T.hasta, tk))) return; }
    for (var i = 0; i < pasos.length; i++) {
      var t = pasos[i], j = junto(t);
      if (!(await volar(j, tk))) return;
      mirar(j.der ? -1 : 1, 0); M.modoOjo = 'feliz'; M.sx = 1.12; M.sy = .88;
      var g = iluminar(t, t.etiqueta, t.n || i + 1, t.de || pasos.length, j);
      host({ op: 'paso', n: t.n || i + 1 });
      setTimeout(function () { if (!M) return; M.modoOjo = 'normal'; M.signo('exclama', { donde: j.der ? 'izq' : 'der', esc: .8, sube: 8 }); }, 480);
      /* lo que pide la app, pero nunca menos que escribir la frase entera y leerla (~60 ms por letra) */
      var txt = t.etiqueta || '';
      await dormir(Math.max(t.ms || 2600, (g.escrita || 0) + 900 + txt.length * 38));
      if (!vivo(tk)) { apagar(g); return; }
      apagar(g);
      await dormir(140);
    }
    if (T.hasta) {
      if (pasos.length && !(await volar(T.hasta, tk))) return;
      M.tgx = 0; M.tgy = 0;
      await dormir(240);
    } else if (!(await desaparecer(tk))) return;
    if (!vivo(tk)) return;
    host({ op: 'fin' });
  }
  function limpiar(todo) {
    R.raiz.querySelectorAll('.wss-anillo,.wss-etq,.wss-px,.wss-puf').forEach(function (n) { n.remove(); });
    if (todo) R.yo.hidden = true;
  }
  /* para la app: corta lo que esté haciendo (llegó otro señalar o se cerró) */
  function cortar() { VIVO++; limpiar(true); }

  W.montar = montar; W.tramo = function (T) { tramo(T); return true; }; W.cortar = cortar; W.mono = function () { return M; };
  return W;
})();
if (document.documentElement.classList.contains('wss-app')) WSS.montar();
