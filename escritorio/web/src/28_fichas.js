/* ================= las fichas en la burbuja (ronda 2 · bloque P): un espejo para pintar =================
   Las fichas de verdad son de la APP (Bandeja.swift): una ventanita suya pegada al monito, armada con datos del portero
   o de la página, que solo acepta clics de una persona. Aquí vive su ESPEJO, para quien quiera enseñarlas dentro de la
   burbuja (la columna «Te esperan» del chat grande, carril 3 · CONTRATO_BANDEJA.md):

     WSFichas.lista()                    → [{id, tono, estado, agente, nombre, color, titulo, detalle, detalle_tipo, sitio,
                                             leyo, boton, boton_id, segundo, segundo_id, con_no, no, casilla, pie, sostener,
                                             partes: [{e, v}] (un borrador: Para · Asunto · Texto)}]
     WSFichas.cuenta()                   → cuántas esperan tu clic
     WSFichas.pintar(caja, {mini, agente, tope})   pinta las fichas en `caja` (y las vuelve a pintar cuando cambian)
     WSFichas.soltar(caja)               deja de pintarlas ahí
     WSFichas.alCambiar(fn)              avisa cuando cambian (fn(lista))

   Un botón de aquí NO decide nada: le pide a la app que lo haga ({op: 'ficha_tocar', id, boton}). La app solo lo acepta
   si hubo un clic de una persona en el monito en ese instante y la ficha ya estaba armada; lo coral (mantener apretado)
   se contesta en su ficha de la app, que se despliega. Todo con textContent: nada se interpreta como HTML. */
var WSFichas = (function () {
  var S = { lista: [], n: 0, plegada: true }, CAJAS = [], OYEN = [];
  var M = { alHost: null };
  var TONOS = { lavanda: 'lav', ambar: 'amb', coral: 'cor', menta: 'men' };

  function host(op) {
    if (M.alHost) { try { M.alHost(op); } catch (e) { } return; }
    try { WSM.host(op); } catch (e) { }
  }
  function nodo(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
  function txt(v, tope) { return typeof v === 'string' ? v.slice(0, tope || 400) : ''; }
  /* de lo que manda la app solo se guardan estos campos, como texto */
  function limpia(f) {
    if (!f || typeof f !== 'object' || !f.id) return null;
    return { id: txt(f.id, 200), tono: TONOS[f.tono] ? f.tono : 'lavanda', estado: txt(f.estado, 20), agente: txt(f.agente, 80),
      nombre: txt(f.nombre, 60), color: /^#[0-9a-fA-F]{6}$/.test(f.color || '') ? f.color : '#8b5cf6', titulo: txt(f.titulo, 300),
      detalle: txt(f.detalle, 4000), detalle_tipo: txt(f.detalle_tipo, 20), sitio: txt(f.sitio, 300), leyo: txt(f.leyo, 200),
      boton: txt(f.boton, 60), boton_id: txt(f.boton_id, 40), segundo: txt(f.segundo, 60), segundo_id: txt(f.segundo_id, 40),
      partes: (Array.isArray(f.partes) ? f.partes : []).slice(0, 6).map(function (p) { return { e: txt(p && p.e, 20), v: txt(p && p.v, 4000) }; })
        .filter(function (p) { return p.e; }),
      conRenglones: Array.isArray(f.renglones) && f.renglones.length > 0, con_no: f.con_no !== false, no: txt(f.no, 20) || 'No', casilla: txt(f.casilla, 120), pie: txt(f.pie, 300), sostener: !!f.sostener };
  }
  function poner(d) {
    var l = (d && Array.isArray(d.fichas) ? d.fichas : []).map(limpia).filter(Boolean);
    S.lista = l; S.n = Math.max(0, +(d && d.n) || 0); S.plegada = !!(d && d.plegada);
    CAJAS.forEach(function (c) { pinta(c); });
    OYEN.forEach(function (fn) { try { fn(S.lista.slice()); } catch (e) { } });
  }
  /* M-3: con el marco del botón tocado (la app solo acepta un clic de persona SOBRE ese botón, y lo gasta) */
  function marco(n) {
    try { var r = n.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; } catch (e) { return null; }
  }
  function tocar(f, boton, n) {
    var o = { op: 'ficha_tocar', id: f.id, boton: boton }, r = n ? marco(n) : null;
    if (r) o.r = r;
    host(o);
  }

  /* una ficha: la misma cara que la de la app (tono, puntito, una frase, botón relleno y «No» en texto) */
  function ficha(f, mini) {
    var n = nodo('div', 'wsf ' + TONOS[f.tono] + (mini ? ' mini' : ''));
    n.setAttribute('data-ficha', f.id);
    var hd = nodo('div', 'wsf-hd'), pt = nodo('i', 'wsf-pt');
    pt.style.setProperty('--a', f.color);
    hd.appendChild(pt); hd.appendChild(nodo('b', null, f.titulo)); n.appendChild(hd);
    if (f.partes.length) {
      /* un borrador de correo: Para · Asunto · Texto, cada uno con su etiqueta y entero (junto5) */
      var ps = nodo('div', 'wsf-partes');
      f.partes.forEach(function (p) {
        var r = nodo('div', 'wsf-parte');
        r.appendChild(nodo('small', null, p.e)); r.appendChild(nodo('span', p.v ? null : 'vacio', p.v || '(vacío)'));
        ps.appendChild(r);
      });
      n.appendChild(ps);
    } else if (f.detalle) {
      var det = nodo('div', 'wsf-det' + (f.detalle_tipo && f.detalle_tipo !== 'texto' ? ' dato' : ''));
      if (f.detalle_tipo === 'url' && f.sitio && f.detalle.toLowerCase().indexOf(f.sitio.toLowerCase()) >= 0) {
        var i = f.detalle.toLowerCase().indexOf(f.sitio.toLowerCase());
        det.appendChild(document.createTextNode(f.detalle.slice(0, i)));
        det.appendChild(nodo('b', null, f.detalle.slice(i, i + f.sitio.length)));
        det.appendChild(document.createTextNode(f.detalle.slice(i + f.sitio.length)));
      } else det.textContent = f.detalle;
      n.appendChild(det);
    }
    if (f.leyo) n.appendChild(nodo('span', 'wsf-leyo', f.leyo));
    var bt = nodo('div', 'wsf-bt');
    if (f.sostener || f.casilla || f.conRenglones) {
      /* lo coral se sostiene, y una casilla se marca, en su ficha de la app: aquí se lleva a ella */
      var ir = nodo('button', 'wsf-btn', 'Ver junto al monito');
      ir.onclick = function () { host({ op: 'ficha_ver', id: f.id, boton: 'ver' }); };
      bt.appendChild(ir);
    } else {
      var b = nodo('button', 'wsf-btn', f.boton);
      b.onclick = function () { tocar(f, f.boton_id, b); };
      bt.appendChild(b);
      if (f.segundo) { var s2 = nodo('button', 'wsf-btn sec', f.segundo); s2.onclick = function () { tocar(f, f.segundo_id, s2); }; bt.appendChild(s2); }
    }
    if (f.con_no) { var no = nodo('button', 'wsf-no', f.no); no.onclick = function () { tocar(f, 'no'); }; bt.appendChild(no); }
    n.appendChild(bt);
    if (f.pie) n.appendChild(nodo('small', 'wsf-de', f.pie));
    return n;
  }
  function pinta(c) {
    var caja = c.caja, o = c.o || {};
    var l = S.lista.filter(function (f) { return !o.agente || f.agente === o.agente; });
    var tope = +o.tope || 0, mas = tope && l.length > tope ? l.length - tope : 0;
    if (mas) l = l.slice(0, tope);
    caja.textContent = '';
    caja.classList.add('wsf-caja');
    l.forEach(function (f) { caja.appendChild(ficha(f, o.mini !== false)); });
    if (mas) { var v = nodo('button', 'wsf-mas', 'Ver todas (' + (l.length + mas) + ')'); v.onclick = function () { host({ op: 'ficha_ver', id: '', boton: 'ver' }); }; caja.appendChild(v); }
    caja.hidden = !l.length && o.esconder !== false;
  }
  function pintar(caja, o) {
    if (!caja) return;
    soltar(caja);
    var c = { caja: caja, o: o || {} };
    CAJAS.push(c); pinta(c);
  }
  function soltar(caja) { CAJAS = CAJAS.filter(function (c) { return c.caja !== caja; }); }
  function alCambiar(fn) { if (typeof fn === 'function') OYEN.push(fn); }

  M.poner = poner; M.pintar = pintar; M.soltar = soltar; M.alCambiar = alCambiar; M.ficha = ficha;
  M.lista = function () { return S.lista.slice(); };
  M.cuenta = function () { return S.n; };
  M.plegada = function () { return S.plegada; };
  return M;
})();
