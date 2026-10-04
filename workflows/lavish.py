#!/usr/bin/env python3
"""WORKSPACE · workflows.lavish — presentación Lavish de un run (HTML autocontenido).

«HTML is the new markdown»: el plan/decisión de un pipeline se emite como un
HTML legible e interactivo con el look WORKSPACE (dorado/oscuro; respeta el
tema claro/oscuro del sistema) que se abre en el browser — para el socio,
no para el parser. Dos artefactos, ambos OPT-IN por spec (paso con
`"present": "lavish"`; sin esa clave NADA cambia):

  · GATE (paso human/escalada en pausa) → `runs/<id>.artifacts/gate-<paso>.html`
    Presenta el contexto de la decisión (pipeline, contrato del paso,
    artefactos del run inlineados como TEXTO escapado, evidencia de los
    verifies) y ofrece **Aprobar / Rechazar** con caja de anotación.
  · PRESENT (paso det/agent verde con `artifact`) →
    `runs/<id>.artifacts/present-<paso>.html` — el artefacto, legible.

SEGURIDAD (misma postura que el resto del runner):
  · Generar el HTML jamás ejecuta contenido del run: todo lo que viene del
    estado va ESCAPADO (html.escape) al markup, y al JS solo viajan run_id y
    step (ya validados por la gramática de ids del runner) vía json.dumps.
    Cero eval/exec; el contenido de artefactos es texto inerte.
  · AUTOCONTENIDO de verdad: CSS+JS inline, cero CDNs/fonts/fetch externos —
    funciona offline (file://) y no filtra nada a la red.
  · Los botones NO saltan el guard Y1 del dev-panel: el modo vivo (fetch al
    POST /api/dev/workflows/decide) solo intenta si la página se sirve por
    http(s) del MISMO origen del panel y hay token; abierta como file:// los
    botones generan el comando exacto (`workspace wf decide … --note …`) listo
    para copiar — fallback honesto, sin abrir superficie nueva.
  · Best-effort: el runner envuelve la generación en try/except — un HTML
    caído jamás toca el resultado del run.
"""
import html as _htmlmod
import json as _json
import os as _os
import re as _re

_ID_RE = _re.compile(r"[A-Za-z0-9._-]+\Z")   # misma gramática que el runner
_MAX_INLINE = 20_000        # chars por artefacto inlineado (cota del driver)

# glifos por estado de paso — espejo semántico de front._wf_step_glyph
_GLYPHS = {
    "ok":            ("✓", "ok"),
    "fail":          ("✗", "bad"),
    "waiting_human": ("⏸", "warn"),
    "skipped":       ("⊝", "dim"),
    "rejected":      ("⊗", "bad"),
    "pending":       ("·", "faint"),
}


def _e(s):
    """Escape HTML de TODO dato del run — nada del estado entra crudo."""
    return _htmlmod.escape("" if s is None else str(s), quote=True)


def _check_step_id(step_id):
    if not isinstance(step_id, str) or not _ID_RE.match(step_id or ""):
        raise ValueError("id de paso inválido: %r" % (step_id,))
    return step_id


def _spec_step(state, step_id):
    for sp in (state.get("spec") or {}).get("steps") or []:
        if sp.get("id") == step_id:
            return sp
    return {}


def _state_step(state, step_id):
    for st in state.get("steps") or []:
        if st.get("id") == step_id:
            return st
    return {}


def _artifact_text(value):
    """(texto, etiqueta, truncado) de UN artefacto: ruta a archivo → se lee
    (cota _MAX_INLINE); dato → JSON legible. Siempre texto inerte."""
    if isinstance(value, str) and _os.path.isfile(value):
        try:
            with open(value, encoding="utf-8", errors="replace") as fh:
                t = fh.read(_MAX_INLINE + 1)
        except OSError as exc:
            return "(ilegible: %s)" % exc, "archivo", False
        lab = "archivo · %s" % value
    else:
        t = value if isinstance(value, str) else _json.dumps(
            value, indent=2, ensure_ascii=False)
        t = t[:_MAX_INLINE + 1]
        lab = "dato del run"
    trunc = len(t) > _MAX_INLINE
    return t[:_MAX_INLINE], lab, trunc


def _strip(state):
    """El pipeline entero como tira de chips — dónde está parado el run."""
    chips = []
    for st in state.get("steps") or []:
        status = st.get("status")
        if status == "ok" and st.get("stub"):
            g, cls = "⊘", "dim"
        else:
            g, cls = _GLYPHS.get(status, ("·", "faint"))
        chips.append('<span class="chip %s"><span class="g">%s</span>%s</span>'
                     % (cls, g, _e(st.get("id"))))
    return '<div class="strip">%s</div>' % "".join(chips)


def _artifacts_html(state):
    arts = state.get("artifacts") or {}
    if not arts:
        return '<p class="empty">el run no tiene artefactos todavía.</p>'
    out, first = [], True
    for k in sorted(arts):
        text, lab, trunc = _artifact_text(arts[k])
        meta = lab + (" · truncado a %dk" % (_MAX_INLINE // 1000)
                      if trunc else "")
        out.append(
            '<details class="art"%s><summary><code>%s</code>'
            '<span class="meta">%s</span></summary><pre>%s</pre></details>'
            % (" open" if first else "", _e(k), _e(meta), _e(text)))
        first = False
    return "".join(out)


def _verifies_html(state):
    rows = []
    for st in state.get("steps") or []:
        v = st.get("verify")
        if not isinstance(v, dict) or v.get("detail") in (None, ""):
            continue
        mark, cls = {True: ("✓", "ok"), False: ("✗", "bad")}.get(
            v.get("ok"), ("·", "dim"))
        rows.append('<li class="%s"><span class="vg">%s</span>'
                    '<code>%s</code><span>%s</span></li>'
                    % (cls, mark, _e(st.get("id")), _e(v.get("detail"))))
    if not rows:
        return ""
    return ('<h2>Evidencia — verifies deterministas</h2>'
            '<ul class="verifies">%s</ul>' % "".join(rows))


def _contract_html(sp):
    c = sp.get("contract") or {}
    if not isinstance(c, dict) or not c:
        return ""
    return ('<dl class="contract">'
            + "".join("<dt>%s</dt><dd>%s</dd>" % (_e(k), _e(v))
                      for k, v in c.items())
            + "</dl>")


def _hero(state, title_extra, badge):
    rid = state.get("run_id", "?")
    chips = ['<span class="tag mono">run %s</span>' % _e(rid),
             '<span class="tag">actualizado %s</span>'
             % _e(str(state.get("updated", "")).replace("T", " "))]
    if state.get("dry"):
        chips.append('<span class="tag">dry</span>')
    if badge:
        chips.append(badge)
    return ('<section class="card hero">'
            '<h1>%s<span class="v">v%s</span></h1>'
            '<div class="sub">%s</div>'
            '<div class="chips">%s</div>%s</section>'
            % (_e(state.get("workflow", "?")), _e(state.get("version", "?")),
               title_extra, "".join(chips), _strip(state)))


def _page(title, body, data=None):
    js = ""
    if data is not None:
        blob = _json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        js = ("<script>\n" + _JS.replace("__LAVISH_DATA__", blob)
              + "\n</script>\n")
    return ('<!doctype html>\n<html lang="es">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">\n'
            '<title>%s</title>\n<style>\n%s</style>\n</head>\n<body>\n'
            '<div class="halo"></div>\n'
            '<header><div class="brand">◆ WORKSPACE</div>'
            '<div class="kicker">%s</div></header>\n'
            '<main>\n%s\n</main>\n'
            '<footer><span>generado por WORKSPACE · workflows/lavish.py</span>'
            '<span>autocontenido — sin CDNs ni red</span></footer>\n'
            '%s</body>\n</html>\n'
            % (_e(title), _CSS, _e("workflow · presentación Lavish"
                                   if data is None else
                                   "gate de workflow · decisión del socio"),
               body, js))


def gate_html(state, step_id):
    """HTML del GATE: el contexto completo para decidir + botones
    Aprobar/Rechazar con anotación. Función pura (state → string)."""
    _check_step_id(step_id)
    sp = _spec_step(state, step_id)
    st = _state_step(state, step_id)
    rid = state.get("run_id", "?")
    who = sp.get("who") or "socio"
    sub = ('el paso <code>%s</code> espera la decisión de <b>%s</b>'
           % (_e(step_id), _e(who)))
    badge = '<span class="tag warn">⏸ en pausa</span>'
    hero = _hero(state, sub, badge)

    ctx = ['<section class="card"><h2>Contexto para decidir</h2>']
    if sp.get("note"):
        ctx.append('<p class="nota">%s</p>' % _e(sp["note"]))
    if st.get("detail"):
        ctx.append('<p class="nota dim">estado del paso: %s</p>'
                   % _e(st["detail"]))
    ctx.append(_contract_html(sp))
    ctx.append('<h2 class="mt">Artefactos del run</h2>')
    ctx.append(_artifacts_html(state))
    ctx.append(_verifies_html(state))
    ctx.append('</section>')

    decision = (
        '<section class="card decision"><h2>Tu decisión</h2>'
        '<label for="nota">Anotación (opcional — queda registrada en el run)'
        '</label>'
        '<textarea id="nota" placeholder="p. ej. «ok, pero renombra el '
        'módulo X antes de integrar»"></textarea>'
        '<div class="btns">'
        '<button id="btn-approve" class="approve" type="button">'
        '✓ Aprobar</button>'
        '<button id="btn-reject" class="reject" type="button">'
        '⊗ Rechazar</button>'
        '</div>'
        '<div id="resultado" class="resultado" hidden>'
        '<div id="res-title"></div>'
        '<pre id="cmd"></pre>'
        '<div class="btns">'
        '<button id="copiar" class="ghost" type="button">⧉ copiar comando'
        '</button>'
        '<button id="redecidir" class="ghost" type="button">↺ cambiar'
        '</button></div>'
        '<div id="estado" class="estado"></div>'
        '<div class="hint">la decisión queda REGISTRADA en el run; aplicarla '
        '(continuar o cerrar) sigue siendo <code>workspace wf resume %s</code>'
        '</div>'
        '</div></section>' % _e(rid))

    title = "Gate · %s · %s" % (step_id, state.get("workflow", "?"))
    return _page(title, hero + "".join(ctx) + decision,
                 data={"run_id": rid, "step": step_id})


def present_html(state, step_id):
    """HTML de PRESENTACIÓN de un paso verde: su artefacto, legible (sin
    botones — es una vista, no un gate). Función pura."""
    _check_step_id(step_id)
    sp = _spec_step(state, step_id)
    aname = sp.get("artifact")
    sub = ('paso <code>%s</code>%s' % (_e(step_id),
           " · rol " + _e(sp["role"]) if sp.get("role") else ""))
    badge = '<span class="tag ok">✓ paso verde</span>'
    hero = _hero(state, sub, badge)
    body = ['<section class="card"><h2>Artefacto del paso</h2>']
    if aname is not None and aname in (state.get("artifacts") or {}):
        text, lab, trunc = _artifact_text(state["artifacts"][aname])
        meta = lab + (" · truncado a %dk" % (_MAX_INLINE // 1000)
                      if trunc else "")
        body.append('<details class="art" open><summary><code>%s</code>'
                    '<span class="meta">%s</span></summary><pre>%s</pre>'
                    '</details>' % (_e(aname), _e(meta), _e(text)))
    else:
        body.append('<p class="empty">el paso no declaró artefacto (o aún '
                    'no existe en el run).</p>')
    body.append(_verifies_html(state))
    body.append('</section>')
    title = "Plan · %s · %s" % (step_id, state.get("workflow", "?"))
    return _page(title, hero + "".join(body), data=None)


# ── escritura como artefacto del run + apertura opcional ───────────────────
def _artifacts_dir(state):
    import workflows as _wf
    d = _os.path.join(_wf.runs_dir(), str(state.get("run_id")) + ".artifacts")
    _os.makedirs(d, exist_ok=True)
    return d


def write_gate(state, step_id):
    """Escribe `runs/<id>.artifacts/gate-<paso>.html` y devuelve la ruta."""
    _check_step_id(step_id)
    path = _os.path.join(_artifacts_dir(state), "gate-%s.html" % step_id)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(gate_html(state, step_id))
    return path


def write_present(state, step_id):
    """Escribe `runs/<id>.artifacts/present-<paso>.html` y devuelve la ruta."""
    _check_step_id(step_id)
    path = _os.path.join(_artifacts_dir(state), "present-%s.html" % step_id)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(present_html(state, step_id))
    return path


def open_in_browser(path):
    """Abre el HTML con el abridor del sistema (mac `open` / win / xdg).
    Best-effort absoluto: False si no se pudo — jamás revienta."""
    import subprocess
    import sys as _sys
    try:
        if _sys.platform == "darwin":
            subprocess.run(["open", path], check=False, timeout=15)
        elif _os.name == "nt":
            _os.startfile(path)                              # noqa: S606
        else:
            subprocess.run(["xdg-open", path], check=False, timeout=15)
        return True
    except Exception:
        try:
            import webbrowser
            return webbrowser.open("file://" + _os.path.abspath(path))
        except Exception:
            return False


# ── look WORKSPACE (inline, autocontenido; claro/oscuro por el sistema) ──────
_CSS = """\
:root{
  --bg:#0b0d12; --bg2:#0e1118; --surface:#12151d; --surface2:#171b26;
  --border:#242a38; --text:#e9e4d6; --dim:#a4a89f; --faint:#707685;
  --gold:#c9a24b; --gold-hi:#e6c87e; --gold-line:#8a723a;
  --green:#6bbf8a; --red:#e0796b; --amber:#d9a441;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: light){
  :root{
    --bg:#f4efe3; --bg2:#faf6ec; --surface:#fffdf6; --surface2:#f6f1e2;
    --border:#e0d7c0; --text:#2c2718; --dim:#6d6754; --faint:#98917c;
    --gold:#8a6d1f; --gold-hi:#6f5714; --gold-line:#c5ad72;
    --green:#2f7d4f; --red:#b4483a; --amber:#8a6415;
  }
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--text);position:relative;min-height:100vh;
  font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;
  padding:34px 18px 46px}
.halo{position:fixed;inset:0;pointer-events:none;
  background:radial-gradient(720px 320px at 50% -80px,rgba(201,162,75,.15),transparent 70%)}
header{max-width:880px;margin:0 auto 26px;display:flex;align-items:baseline;
  gap:14px;flex-wrap:wrap;border-bottom:1px solid var(--border);
  padding-bottom:14px;position:relative}
header:after{content:"";position:absolute;left:0;bottom:-1px;width:180px;
  height:1px;background:linear-gradient(90deg,var(--gold),transparent)}
.brand{color:var(--gold);font-weight:700;letter-spacing:.14em;font-size:15px}
.kicker{color:var(--faint);font-size:11px;letter-spacing:.22em;text-transform:uppercase}
main{max-width:880px;margin:0 auto;display:grid;gap:18px;position:relative}
.card{background:linear-gradient(165deg,var(--surface2),var(--surface));
  border:1px solid var(--border);border-radius:14px;padding:22px 26px}
h1{margin:0;font-size:26px;letter-spacing:.01em}
h1 .v{color:var(--gold-hi);font-size:14px;font-weight:600;margin-left:8px}
h2{margin:0 0 12px;font-size:12px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--gold)}
h2.mt{margin-top:20px}
.sub{color:var(--dim);margin-top:6px}
.sub b{color:var(--text)}
code{font-family:var(--mono);font-size:.92em;background:var(--bg2);
  border:1px solid var(--border);border-radius:5px;padding:1px 6px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.tag{font-size:11px;color:var(--dim);border:1px solid var(--border);
  border-radius:999px;padding:3px 10px;background:var(--bg2)}
.tag.mono{font-family:var(--mono)}
.tag.warn{color:var(--amber);border-color:var(--amber)}
.tag.ok{color:var(--green);border-color:var(--green)}
.strip{display:flex;gap:6px;flex-wrap:wrap;margin-top:16px}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;
  border:1px solid var(--border);border-radius:8px;padding:4px 10px;
  color:var(--dim);background:var(--bg2)}
.chip .g{font-size:13px}
.chip.ok .g{color:var(--green)}
.chip.bad,.chip.bad .g{color:var(--red)}
.chip.bad{border-color:rgba(224,121,107,.5)}
.chip.warn{border-color:var(--gold-line);color:var(--gold-hi);
  box-shadow:0 0 12px -4px var(--gold)}
.chip.warn .g{color:var(--amber)}
.chip.dim,.chip.dim .g{color:var(--faint)}
.chip.faint,.chip.faint .g{color:var(--faint)}
.chip.faint{border-style:dashed}
.nota{color:var(--dim);margin:0 0 12px}
.nota.dim{color:var(--faint);font-size:13px}
.contract{display:grid;grid-template-columns:110px 1fr;gap:6px 14px;margin:0 0 16px}
.contract dt{color:var(--gold-hi);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase}
.contract dd{margin:0;color:var(--dim);font-size:13.5px}
details.art{border:1px solid var(--border);border-radius:10px;
  background:var(--bg2);margin-bottom:10px;overflow:hidden}
details.art summary{cursor:pointer;padding:10px 14px;display:flex;gap:10px;
  align-items:baseline;list-style:none}
details.art summary::-webkit-details-marker{display:none}
details.art summary:before{content:"▸";color:var(--gold);font-size:11px}
details.art[open] summary:before{content:"▾"}
details.art .meta{font-size:11px;color:var(--faint);margin-left:auto;
  font-family:var(--mono)}
details.art pre{margin:0;border:0;border-top:1px solid var(--border);
  border-radius:0}
pre{font-family:var(--mono);font-size:12.5px;background:var(--bg2);
  border:1px solid var(--border);border-radius:9px;padding:12px 14px;
  white-space:pre-wrap;word-break:break-word;max-height:420px;overflow:auto;
  margin:8px 0}
.verifies{list-style:none;margin:0;padding:0}
.verifies li{padding:5px 0;font-size:13px;color:var(--dim);display:flex;
  gap:9px;align-items:baseline}
.verifies .vg{width:14px;text-align:center;flex:none}
.verifies li.ok .vg{color:var(--green)}
.verifies li.bad .vg{color:var(--red)}
.empty{color:var(--faint);font-size:13px}
label{display:block;font-size:12px;color:var(--dim);margin:2px 0 8px}
textarea{width:100%;min-height:86px;background:var(--bg2);
  border:1px solid var(--border);border-radius:9px;color:var(--text);
  font:inherit;padding:10px 12px;resize:vertical}
textarea:focus{outline:none;border-color:var(--gold-line);
  box-shadow:0 0 0 2px rgba(201,162,75,.18)}
.btns{display:flex;gap:12px;margin-top:14px;flex-wrap:wrap}
button{font:inherit;cursor:pointer;border-radius:9px;padding:10px 22px;
  border:1px solid transparent;
  transition:transform .12s ease,box-shadow .12s ease,background .12s ease}
button:disabled{opacity:.45;cursor:default;transform:none!important;
  box-shadow:none!important}
.approve{background:linear-gradient(180deg,var(--gold-hi),var(--gold));
  color:#171204;font-weight:700;box-shadow:0 2px 14px -4px rgba(201,162,75,.55)}
.approve:hover:not(:disabled){transform:translateY(-1px);
  box-shadow:0 4px 20px -4px rgba(201,162,75,.7)}
.reject{background:transparent;border-color:rgba(224,121,107,.55);
  color:var(--red);font-weight:600}
.reject:hover:not(:disabled){background:rgba(224,121,107,.12)}
.ghost{background:transparent;border-color:var(--border);color:var(--dim);
  font-size:12px;padding:6px 12px}
.ghost:hover{color:var(--gold-hi);border-color:var(--gold-line)}
.resultado{margin-top:16px;border-top:1px dashed var(--border);padding-top:14px}
.resultado[hidden]{display:none}
#res-title{font-weight:700;letter-spacing:.06em}
#res-title.ok{color:var(--green)}
#res-title.bad{color:var(--red)}
.estado{font-size:12px;color:var(--dim);margin-top:10px}
.estado.live{color:var(--green)}
.hint{font-size:12px;color:var(--faint);margin-top:10px}
body.decidido-ok .decision{border-color:rgba(107,191,138,.5)}
body.decidido-no .decision{border-color:rgba(224,121,107,.5)}
footer{max-width:880px;margin:34px auto 0;color:var(--faint);font-size:11px;
  letter-spacing:.08em;border-top:1px solid var(--border);padding-top:12px;
  display:flex;gap:14px;flex-wrap:wrap;justify-content:space-between}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

# JS del gate: construye el comando `workspace wf decide …` (fallback SIEMPRE
# disponible) e intenta el modo vivo SOLO mismo-origen http(s) + token (el
# dev-panel) — jamás debilita Y1: sin token/origen el POST muere en 403.
_JS = """\
"use strict";
var LAVISH = __LAVISH_DATA__;
function $id(x){ return document.getElementById(x); }
function shq(s){ return "'" + String(s).replace(/'/g, "'\\\\''") + "'"; }
function cmdFor(d, note){
  var c = "workspace wf decide " + LAVISH.run_id + " " + LAVISH.step + " " + d;
  if(note) c += " --note " + shq(note);
  return c;
}
function tryLive(d, note, cb){
  if(location.protocol !== "http:" && location.protocol !== "https:"){
    cb(false); return;
  }
  var token = "";
  try{
    token = new URLSearchParams(location.search).get("token")
      || window.WORKSPACE_TOKEN || "";
  }catch(e){}
  if(!token){ cb(false); return; }
  var done = false;
  function fin(ok){ if(!done){ done = true; cb(ok); } }
  try{
    fetch("/api/dev/workflows/decide", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-WORKSPACE-Token": token},
      body: JSON.stringify({run_id: LAVISH.run_id, step: LAVISH.step,
                            decision: d, note: note})
    }).then(function(r){ return r.json(); })
      .then(function(j){ fin(!!(j && j.ok)); })
      .catch(function(){ fin(false); });
    setTimeout(function(){ fin(false); }, 4000);
  }catch(e){ fin(false); }
}
function decide(d){
  var note = ($id("nota").value || "").trim();
  $id("btn-approve").disabled = true;
  $id("btn-reject").disabled = true;
  document.body.classList.remove("decidido-ok", "decidido-no");
  document.body.classList.add(d === "approve" ? "decidido-ok" : "decidido-no");
  $id("cmd").textContent = cmdFor(d, note);
  var t = $id("res-title");
  t.textContent = d === "approve" ? "✓ APROBAR" : "⊗ RECHAZAR";
  t.className = d === "approve" ? "ok" : "bad";
  $id("resultado").hidden = false;
  $id("estado").textContent = "…";
  $id("estado").className = "estado";
  tryLive(d, note, function(ok){
    $id("estado").textContent = ok
      ? "decisión registrada en el run (vía dev-panel)."
      : "copia el comando y córrelo en la terminal para registrarla.";
    if(ok) $id("estado").className = "estado live";
  });
}
function copiar(){
  var t = $id("cmd").textContent;
  function fb(){
    var ta = document.createElement("textarea");
    ta.value = t; document.body.appendChild(ta); ta.select();
    try{ document.execCommand("copy"); }catch(e){}
    document.body.removeChild(ta);
  }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(t).catch(fb);
  } else { fb(); }
  $id("copiar").textContent = "✓ copiado";
  setTimeout(function(){ $id("copiar").textContent = "⧉ copiar comando"; }, 1600);
}
function redecidir(){
  $id("btn-approve").disabled = false;
  $id("btn-reject").disabled = false;
  $id("resultado").hidden = true;
  document.body.classList.remove("decidido-ok", "decidido-no");
}
document.addEventListener("DOMContentLoaded", function(){
  var a = $id("btn-approve"), r = $id("btn-reject");
  var c = $id("copiar"), z = $id("redecidir");
  if(a) a.addEventListener("click", function(){ decide("approve"); });
  if(r) r.addEventListener("click", function(){ decide("reject"); });
  if(c) c.addEventListener("click", copiar);
  if(z) z.addEventListener("click", redecidir);
});
"""
