/* ================= la guía: «Recorrido con foco» (H5-a) =================
   Cinco pasos, los mismos que en el hub: apaga todo menos una parte, la explica en una frase y «Siguiente». Se abre
   con el «?» del riel (encima del engrane) y, una sola vez, sola la primera vez; con «Esc» o «Listo» no vuelve a salir
   sola, pero el «?» sigue ahí (y «Ver la guía otra vez» en Configuración › Ayuda). Un paso cuya parte no se ve (el
   panel cerrado, una pantalla angosta) se salta.
   «Ya la vi» se recuerda en Workspace (/api/front/guia → lo de esta computadora), no en el navegador: la página se
   sirve en un puerto distinto en cada arranque y para el navegador cada puerto es otro sitio, con su recuerdo vacío
   (salía cada vez). El recuerdo de antes (el de este navegador) se respeta y se pasa a Workspace. */
var GUIA_PASOS = [
  { sel: '#rail .lst', t: 'Tus agentes', d: 'Cada monito es un agente con su cerebro. Un clic y hablas con él.' },
  { sel: '#motor', t: 'Su motor', d: 'Con qué programa piensa (Claude Code, Codex…). Se cambia aquí y se guarda solo.' },
  { sel: '.box', t: 'Hablarle', d: 'Escribe aquí. Es la misma conversación que en el hub de la terminal.' },
  { sel: '#side', t: 'Lo suyo', d: 'Sus skills, sus sesiones y lo que va haciendo.' },
  { sel: '#bGuia', t: 'Siempre a la mano', d: 'Si te pierdes, este «?» vuelve a empezar, cuando quieras.' }
];
function guiaRect(n) {
  var e = document.querySelector(GUIA_PASOS[n].sel); if (!e) return null;
  var r = e.getBoundingClientRect();
  return r.width > 4 && r.height > 4 && r.right > 0 && r.left < innerWidth ? r : null;
}
function guia() {
  cerrarCapas(); quitarTip();
  var vieja = document.querySelector('.grecorrido'); if (vieja) vieja.remove();
  guiaAnotar();
  var a = activo(), k = -1;
  var capa = el('div', 'grecorrido'), foco = el('div', 'gfoco'), ficha = el('div', 'gficha');
  capa.style.setProperty('--c', a ? a.c : '#ff4fa3');
  capa.appendChild(foco); capa.appendChild(ficha); document.body.appendChild(capa);
  function cerrar() { capa.remove(); document.removeEventListener('keydown', teclas, true); window.removeEventListener('resize', pinta); }
  function paso(d) {
    var n = k + d;
    while (n >= 0 && n < GUIA_PASOS.length && !guiaRect(n)) n += d;
    if (n >= GUIA_PASOS.length) return cerrar();
    if (n < 0) return;
    k = n; pinta();
  }
  function boton(txt, cls, fn) { var b = el('button', cls, txt); b.onclick = function (e) { e.stopPropagation(); fn(); }; return b; }
  function pinta() {
    var r = guiaRect(k); if (!r) return paso(1);
    foco.style.left = (r.left - 6) + 'px'; foco.style.top = (r.top - 6) + 'px';
    foco.style.width = (r.width + 12) + 'px'; foco.style.height = (r.height + 12) + 'px';
    var visibles = GUIA_PASOS.filter(function (_p, i) { return guiaRect(i); }).length;
    var num = GUIA_PASOS.slice(0, k + 1).filter(function (_p, i) { return guiaRect(i); }).length;
    var ultimo = !GUIA_PASOS.slice(k + 1).some(function (_p, i) { return guiaRect(k + 1 + i); });
    ficha.textContent = '';
    var cab = el('div', 'gcab'); cab.appendChild(el('b', null, num + ' de ' + visibles)); cab.appendChild(el('span', null, ' · ' + GUIA_PASOS[k].t));
    var x = boton('Esc sale', 'gesc', cerrar); cab.appendChild(x); ficha.appendChild(cab);
    ficha.appendChild(el('p', null, GUIA_PASOS[k].d));
    var pie = el('div', 'gpie');
    pie.appendChild(boton(ultimo ? 'Listo' : 'Siguiente', 'gsig', function () { paso(1); }));
    if (num > 1) pie.appendChild(boton('Atrás', 'gatr', function () { paso(-1); }));
    var pts = el('span', 'gpts'); for (var i = 0; i < visibles; i++) pts.appendChild(el('i', i < num ? 'on' : null)); pie.appendChild(pts);
    ficha.appendChild(pie);
    var fw = Math.min(300, innerWidth - 24), fh = ficha.offsetHeight || 150, lx = r.right + 18, ty = r.top;
    if (lx + fw > innerWidth - 12) lx = r.left - fw - 18;
    if (lx < 12) { lx = Math.max(12, Math.min(innerWidth - fw - 12, r.left + r.width / 2 - fw / 2)); ty = r.bottom + 16 + fh < innerHeight ? r.bottom + 16 : r.top - fh - 16; }
    ficha.style.width = fw + 'px'; ficha.style.left = lx + 'px';
    ficha.style.top = Math.max(12, Math.min(innerHeight - fh - 12, ty)) + 'px';
    var sig = ficha.querySelector('.gsig'); if (sig) sig.focus();
  }
  function teclas(e) {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cerrar(); }
    else if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); paso(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); e.stopPropagation(); paso(-1); }
  }
  capa.onclick = function (e) { e.stopPropagation(); };
  document.addEventListener('keydown', teclas, true);
  window.addEventListener('resize', pinta);
  paso(1);
}
function guiaAnotar() {
  var ya = S.guiaVista; S.guiaVista = true; CFG_LOCAL.set('guiaVista', true);
  if (!ya) post('/api/front/guia', { vista: true }).catch(function () {});
}
function guiaPrimeraVez() {
  if (S.guiaVista) return;
  if (CFG_LOCAL.get('guiaVista')) return guiaAnotar();
  if (S.agentes.length && !document.querySelector('.velo')) guia();
}
