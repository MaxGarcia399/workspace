"""Read-only status formatting; countdowns derive from vendor reset timestamps.

Lo comparten las dos barras que Workspace pinta DENTRO de un CLI ajeno:
  · el pie opt-in de Codex (codex_status.footer, WORKSPACE_CODEX_LIVE_BAR=1);
  · la statusLine nativa de Antigravity (antigravity_usage.main → aquí).
Solo formatea lo que el proveedor publica (cuotas, % de contexto): desconocido
se dice como tal, nunca como 0. Colores = paleta del tema del hub (tuitheme),
nada fijo; sin color (NO_COLOR, TERM=dumb, tema B/N) sale texto plano.
"""
import math
import os
import json
import time
import re
from pathlib import Path


def t(key, es, en=None, **kw):
    """i18n falla-suave: catálogo (lang/<code>/motorbar.py) → ES/EN inline."""
    s = es
    try:
        import i18n
        v = i18n.t(key, **kw) if kw else i18n.t(key)
        if v != key:
            return v
        if en is not None and i18n.lang() == "en":
            s = en
    except Exception:
        pass
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def clean(value):
    return re.sub(r'[\x00-\x1f\x7f]', '', str(value)).replace('#','').strip()

def duration(seconds):
    seconds=max(0,int(seconds))
    d,seconds=divmod(seconds,86400);h,seconds=divmod(seconds,3600);m,_=divmod(seconds,60)
    return ('%dd %dh' % (d,h)) if d else ('%dh %02dm' % (h,m)) if h else '%dm' % m


def colors(enabled=None):
    """Colores de la paleta del HUB para pintar una barra: dict con
    accent/hi/text/dim/ok/warn/bad/R/B (secuencias ANSI). `enabled=None` →
    según la terminal (tuitheme.color_mode); False → todo vacío (texto plano)."""
    blank = dict.fromkeys(("accent", "hi", "text", "dim", "ok", "warn", "bad",
                           "R", "B"), "")
    if enabled is False:
        return blank
    try:
        import tuitheme
        P = tuitheme.palette()
        if P.mode == "mono" and enabled is None:
            return blank
        return {"accent": P.B, "hi": P.C, "text": P.WH, "dim": P.DIM,
                "ok": P.OK, "warn": P.BAD, "bad": P.ERR, "R": P.R, "B": P.BO}
    except Exception:
        return blank


def _paint(K, role, text):
    if not text or not K or not K.get(role):
        return text
    return "%s%s%s" % (K[role], text, K.get("R") or "\033[0m")


def window(label,used,reset,now=None,K=None,reset_passed=None):
    """«5h ███░░ 30% usado · reinicia 2h 05m». `reset_passed` (texto) se usa
    cuando el reinicio YA pasó: el % viejo ya no vale y se dice que la ventana
    se reinició, en vez de mostrar un número muerto. K = colors() o None."""
    now=time.time() if now is None else now
    try:
        used=float(used)
        if not math.isfinite(used) or not 0<=used<=100: raise ValueError()
    except (TypeError,ValueError):
        return _paint(K,'dim',clean(label)+' · '+t('motorbar.quota_none','cuota sin datos','no quota data'))
    if reset_passed and reset is not None:
        try:
            if float(reset)<=now:
                return _paint(K,'dim',clean(label))+' · '+_paint(K,'ok',reset_passed)
        except (TypeError,ValueError):
            pass
    fill=round(used/100*10)
    role='bad' if used>=90 else 'warn' if used>=70 else 'accent'
    bar=_paint(K,role,'█'*fill)+_paint(K,'dim','░'*(10-fill))
    result='%s %s %s' % (_paint(K,'dim',clean(label)),bar,
                         t('motorbar.used','{pct}% usado','{pct}% used',pct='%.0f' % used))
    if reset is not None:
        try:
            reset=float(reset)
            if math.isfinite(reset):
                result += ' · '+_paint(K,'dim',
                    t('motorbar.resets_in','reinicia {d}','resets in {d}',d=duration(reset-now)) if reset>now
                    else t('motorbar.reset_unconfirmed','reinicio pendiente de confirmar','reset not yet confirmed'))
        except (ValueError,TypeError):pass
    return result

def brain_version(brain):
    try:
        text=(Path(brain)/'STATE/brain-version.md').read_text(encoding="utf-8")[:2000]
        found=re.search(r'v?\d+\.\d+\.\d+',text)
        return 'Brain '+found.group() if found else ''
    except OSError:return ''


def agent_for_dir(path, max_up=4):
    """Nombre visible del agente dueño de `path` (su cerebro o una subcarpeta):
    el primer `.workspace/agent.json` subiendo como mucho `max_up` niveles.
    Solo lectura, acotado; '' si no hay agente (agy abierto fuera de un
    cerebro)."""
    try:
        p = os.path.realpath(str(path or ""))
    except Exception:
        return ""
    for _ in range(max_up + 1):
        if not p:
            break
        for rel in (os.path.join(".workspace", "agent.json"), "agent.json"):
            f = os.path.join(p, rel)
            try:
                if os.path.isfile(f) and os.path.getsize(f) < 262144:
                    with open(f, encoding="utf-8") as fh:
                        d = json.load(fh)
                    if isinstance(d, dict) and (d.get("display") or d.get("name")):
                        return clean(d.get("display") or d.get("name"))
            except (OSError, ValueError):
                pass
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return ""


#: Modo de ejecución que agy publica en la statusLine (`cycle_mode`) → qué
#: significa para el socio, en corto.
_MODE_TEXT = {
    "accept-edits": ("motorbar.mode.accept_edits", "edita sin preguntar", "edits without asking"),
    "default": ("motorbar.mode.default", "pide permiso al editar", "asks before editing"),
    "plan": ("motorbar.mode.plan", "modo plan", "plan mode"),
}


def _family(model):
    """'gemini' para modelos Gemini; '3p' para los de terceros (cuotas de agy
    `gemini-*` vs `3p-*`)."""
    return "gemini" if "gemini" in str(model or "").lower() else "3p"


def _bucket_label(name):
    tail = name.split("-", 1)[1] if "-" in name else name
    if tail == "weekly":
        return t("motorbar.week", "semana", "week")
    return tail


def antigravity_lines(payload,now=None,color=None):
    """Líneas de la statusLine de Workspace en Antigravity (se APILA debajo de
    la nativa: stack_with_default). 1ª: agente · modelo · contexto · modo ·
    estado · rama · versión del cerebro. 2ª: las cuotas del modelo en uso
    (5h y semana) en UNA línea. El agente sale del payload (workspace.
    project_dir / cwd → .workspace/agent.json); el env del lanzamiento es el
    respaldo. `color=None` → según la terminal; False → texto plano."""
    import antigravity_usage as A
    now=time.time() if now is None else now
    K=colors(color)
    model=payload.get('model') or {};ctx=payload.get('context_window') or {};vcs=payload.get('vcs') or {}
    ws=payload.get('workspace') if isinstance(payload.get('workspace'),dict) else {}
    model_name=clean(model.get('display_name') or model.get('id') or 'Gemini') if isinstance(model,dict) else 'Gemini'
    title=[_paint(K,'text',model_name)]
    try:
        pct=float(ctx.get('used_percentage'))
        if math.isfinite(pct) and 0<=pct<=100:
            title.append(_paint(K,'warn' if pct>=80 else 'dim',
                                t('motorbar.context','contexto {pct}%','context {pct}%',pct='%.0f' % pct)))
    except (ValueError,TypeError,AttributeError):pass
    mode=_MODE_TEXT.get(str(payload.get('cycle_mode') or payload.get('execution_mode') or ''))
    if mode:title.append(_paint(K,'dim',t(*mode)))
    if isinstance(vcs,dict) and vcs.get('branch'):
        title.append(_paint(K,'dim',clean(vcs['branch'])+(' ± '+t('motorbar.dirty','cambios','changes') if vcs.get('dirty') else '')))
    state=clean(payload.get('agent_state') or '')
    if state and state not in ('idle','initializing'):title.append(_paint(K,'hi',state))
    where=ws.get('project_dir') or payload.get('cwd') or os.environ.get('WORKSPACE_BRAIN','')
    identity=agent_for_dir(where) if where else ''
    if not identity:
        try:
            identity=json.loads(os.environ.get('WORKSPACE_AGENT_UI','{}')).get('name','')
        except (ValueError,AttributeError):identity=''
    if identity:title.insert(0,_paint(K,'accent',(K.get('B') or '')+clean(identity)))
    version=brain_version(where)
    if version:title.append(_paint(K,'dim',version))
    lines=[_paint(K,'dim',' · ').join(title)]
    snap=A.snapshot(payload,now)
    if snap:
        fam=_family(model.get('id') if isinstance(model,dict) else '')
        mine=[b for b in snap['buckets'] if b['label'].split('-',1)[0]==fam] or snap['buckets']
        lines.append(_paint(K,'dim','  │  ').join(
            window(_bucket_label(b['label']),b['used_percent'],b['resets_at'],now,K=K)
            for b in mine[:3]))
    else:lines.append(_paint(K,'dim',t('motorbar.agy_no_quota','Cuota: sin datos del proveedor','Quota: no data from the provider')))
    try:width=max(16,min(1000,int(payload.get('terminal_width') or 100)))
    except (TypeError,ValueError):width=100
    import hublayout as H
    return [H.clip(line,width-1) for line in lines]
