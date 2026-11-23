/* ================= la tarjeta de permiso de su motor (salió de 20_escritorio.js, ronda 2 · carril fichas) =================
   Su ciclo (puro) y lo que pinta dentro de la burbuja. La burbuja (20_escritorio.js) solo la llama: WSMPermiso.ciclo y
   WSMPermiso.pintar(tarjeta, pedido, {agente, leido, host, decidir}). Todo con textContent. */
var WSMPermiso = (function () {
  var DECIDE = { permitir: 'Permitir', permitir_siempre: 'Siempre', negar: 'No' };
  /* ---------- la tarjeta de permiso de su motor: un ciclo, una tarjeta por pedido ----------
     llega → la tarjeta · tu clic → se va al momento y queda una línea corta («Listo, le di permiso») que se va sola ·
     el mismo pedido otra vez (la foto de la página tarda en enterarse) → nada · otro pedido → otra tarjeta. Nunca la
     tarjeta contestada se queda a la vista, ni sale otra para el mismo pedido. Pura (sin DOM): se prueba sola. */
  var CICLO = {
    nuevo: function () { return { cual: null, decididos: {}, listo: null, negado: '' }; },
    firma: function (ev) { return String((ev && (ev.texto || ev.detalle)) || ''); },
    /* lo que dice la foto: un pedido (con id) o ninguno (id null). → 'nueva' | 'igual' | 'fue' (se fue sin tu clic) */
    llega: function (c, ev, ahora) {
      var hay = !!(ev && (ev.id || ev.en_terminal));
      if (!hay) {
        if (!c.cual) return 'igual';
        var suyo = !c.decididos[c.cual.id];
        c.cual = null;
        if (suyo) { c.listo = { texto: 'Ya no lo necesita: siguió sin eso.', tipo: 'fue', hasta: ahora + 1800 }; return 'fue'; }
        return 'igual';
      }
      if (ev.id && c.decididos[ev.id]) return 'igual';          /* ya lo contestaste: nunca otra tarjeta */
      if (c.cual && c.cual.id === ev.id) { c.cual = ev; return 'igual'; }
      ev.otraVez = !!(c.negado && c.negado === CICLO.firma(ev));
      c.cual = ev; c.listo = null;
      return 'nueva';
    },
    decide: function (c, id, d, ahora) {
      if (!c.cual || c.cual.id !== id || c.decididos[id]) return false;
      c.decididos[id] = d;
      c.negado = d === 'negar' ? CICLO.firma(c.cual) : '';
      c.listo = { texto: d === 'negar' ? 'Listo, no lo hará.' : d === 'permitir_turno' ? 'Listo: le di permiso para eso, solo en este trabajo.'
        : d === 'permitir_siempre' ? 'Listo, le di permiso (y ya no te lo vuelve a pedir).' : 'Listo, le di permiso.',
        tipo: d === 'negar' ? 'no' : 'si', hasta: ahora + 1600 };
      c.cual = null;
      return true;
    },
    tic: function (c, ahora) { if (c.listo && ahora >= c.listo.hasta) { c.listo = null; return true; } return false; }
  };
  /* un ojo pixel chiquito (el del ojito de las manos) */
  function ojito() {
    if (!document.createElementNS) return el('i', 'ojo');
    var NSV = 'http://www.w3.org/2000/svg', s = document.createElementNS(NSV, 'svg');
    s.setAttribute('viewBox', '0 0 11 7'); s.setAttribute('width', '15'); s.setAttribute('height', '10'); s.setAttribute('class', 'ojo');
    [[3, 0, 5, 1], [1, 1, 2, 1], [8, 1, 2, 1], [0, 2, 1, 3], [10, 2, 1, 3], [1, 5, 2, 1], [8, 5, 2, 1], [3, 6, 5, 1], [4, 2, 3, 3]].forEach(function (r) {
      var q = document.createElementNS(NSV, 'rect');
      q.setAttribute('x', r[0]); q.setAttribute('y', r[1]); q.setAttribute('width', r[2]); q.setAttribute('height', r[3]); s.appendChild(q);
    });
    return s;
  }
  /* la marca de «ya leyó tu pantalla en esta conversación» (si su motor pide permiso después, lo sabes) */
  function marcaLeyo(pm, leido) {
    var l = leido || (pm && pm.leyo ? { app: pm.leyo_app || '' } : null);
    if (!l) return null;
    var m = el('div', 'wsm-leyo');
    m.appendChild(ojito());
    m.appendChild(el('span', null, (l.ajeno ? 'Leyó contenido de otros' : 'Leyó tu pantalla') + ' en esta conversación' + (l.app ? ' (' + l.app + ')' : '')));
    m.title = 'Lo que viste en pantalla pudo traer instrucciones de otros: revisa que esto sea lo que tú pediste.';
    return m;
  }
  /* La tarjeta de un permiso de su motor, dentro de `T` (la caja de la tarjeta de la burbuja, ya vacía). */
  /* ¿La app enseña los permisos de su motor como FICHAS junto al monito? (ronda 2: lo dice al presentarse) */
  function enFichas() {
    try { var a = WSM.s.app; return !!(a && Array.isArray(a.capacidades) && a.capacidades.indexOf('fichas') >= 0); } catch (e) { return false; }
  }
  function pintar(T, pm, x) {
    if (enFichas() && pm.id && !pm.en_terminal) {
      /* su ficha está junto al monito (la arma la app y solo acepta tu clic): aquí solo se dice dónde */
      T.className = 'wsm-tarjeta perm enficha';
      T.appendChild(el('small', null, 'Te pide permiso'));
      T.appendChild(el('p', null, 'Su ficha está junto al monito.'));
      var cf = el('div', 'chips'), v = el('button', 'chip p', 'Ver la ficha');
      v.onclick = function () { x.host({ op: 'ficha_ver', id: String(pm.id), boton: 'ver' }); };
      cf.appendChild(v); T.appendChild(cf);
      return;
    }
    T.className = 'wsm-tarjeta perm';
    T.appendChild(el('small', null, pm.en_terminal ? 'Te pide permiso en su terminal' : pm.otraVez ? 'Lo vuelve a pedir' : 'Te pide permiso'));
    T.appendChild(el('p', null, pm.texto || 'Quiere usar una de sus herramientas.'));
    var ml = marcaLeyo(pm, x.leido); if (ml) T.appendChild(ml);
    if (pm.detalle) { var d = el('details', 'wsm-det'); d.appendChild(el('summary', null, 'Ver detalle')); d.appendChild(el('pre', null, pm.detalle)); T.appendChild(d); }
    var ch = el('div', 'chips');
    if (pm.en_terminal || !(pm.opciones || []).length) {
      var t = el('button', 'chip p', 'Ir a la terminal'); t.onclick = function () { x.host({ op: 'terminal', agente: x.agente.id }); }; ch.appendChild(t);
    } else pm.opciones.forEach(function (o) {
      var txt = o === 'permitir_turno' ? 'Sí, y lo demás de esa carpeta' : DECIDE[o] || o;
      var b = el('button', 'chip' + (o === 'permitir' ? ' p' : '') + (o === 'permitir_turno' ? ' grupo' : ''), txt);
      b.onclick = function () { x.decidir(pm, o); };
      ch.appendChild(b);
    });
    T.appendChild(ch);
    if (pm.grupo && (pm.opciones || []).indexOf('permitir_turno') >= 0)
      T.appendChild(el('div', 'wsm-grupo', pm.grupo.nota || pm.grupo.texto || 'Solo mientras hace este trabajo.'));
    T.appendChild(el('div', 'wsm-quien', 'Lo pide ' + (pm.motor || 'su motor') + '. Solo pasa si tú lo eliges.'));
  }
  return { ciclo: CICLO, DECIDE: DECIDE, pintar: pintar, marcaLeyo: marcaLeyo, ojito: ojito, enFichas: enFichas };
})();
