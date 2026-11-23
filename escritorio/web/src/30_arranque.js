/* La app de la Mac: arma el monito y avisa que está listo (el puente le manda los agentes de Workspace). En el boceto
   no corre: ahí lo arma boceto.js con su escritorio de ejemplo.
   La app contesta con su versión (WSM.app): si no contesta, es una app de antes que esta burbuja y algunos botones no
   le llegarían; la barra lo dice en una línea (en vez de botones que no hacen nada). */
if (document.documentElement.classList.contains('wsm-app')) {
  WSM.montar(document.getElementById('wsm'));
  if (typeof WSMVoz !== 'undefined') WSMVoz.auto();          /* el micrófono de la caja (28_voz.js) */
  try { window.webkit.messageHandlers.ws.postMessage({ op: 'listo' }); } catch (e) { }
  setTimeout(function () { if (!WSM.s.app) WSM.app(null); }, 4000);
}
