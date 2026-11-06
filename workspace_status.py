"""Read-only status formatting; countdowns derive from vendor reset timestamps.

Lo comparten las barras que Workspace pinta DENTRO de un CLI ajeno:
  · el pie opt-in de Codex (codex_status.footer, WORKSPACE_CODEX_LIVE_BAR=1);
  · la statusLine nativa de Antigravity (antigravity_usage.main → aquí);
  · la statusLine nativa de GitHub Copilot y la de Cursor (motor_statusline.main
    → copilot_lines / cursor_lines).
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


def _num(value):
    """Número finito ≥0 del JSON del motor, o None (bool/texto/NaN = no hay)."""
    if isinstance(value,bool):return None
    try:
        f=float(value)
    except (TypeError,ValueError):return None
    return f if math.isfinite(f) and f>=0 else None


def _copilot_context(ctx):
    """% de la ventana de contexto OCUPADA, o None si Copilot aún no lo midió.
    VERIFICADO 1.0.105: `current_context_used_percentage` (sobre
    current_context_tokens: prompt de sistema + historial) es la ocupación
    real; `used_percentage` es otra cosa (tokens gastados / ventana) y antes del
    primer mensaje AMBOS llegan en 0 sin nada medido → «desconocido», no 0%."""
    if not isinstance(ctx,dict):return None
    cur=_num(ctx.get('current_context_tokens'))
    if cur:
        pct=_num(ctx.get('current_context_used_percentage'))
        if pct is None:
            size=_num(ctx.get('context_window_size'))
            pct=(cur/size*100) if size else None
        return pct if pct is not None and pct<=100 else None
    if 'current_context_tokens' in ctx:return None
    # versión sin los campos current_*: el % general, solo con tokens medidos
    if _num(ctx.get('total_tokens')):
        pct=_num(ctx.get('used_percentage'))
        return pct if pct is not None and pct<=100 else None
    return None


def _dict(payload,key):
    v=payload.get(key)
    return v if isinstance(v,dict) else {}


def _identity(payload,env,engine,K):
    """(partes, carpeta) comunes a las barras de motor: el agente (del cerebro
    de la carpeta o, si Workspace abrió ESTE motor, el del arranque) y la
    pestaña (solo en una sesión de Workspace de este motor)."""
    ws=_dict(payload,'workspace')
    where=ws.get('current_dir') or payload.get('cwd') or env.get('WORKSPACE_BRAIN','')
    mine=str(env.get('WORKSPACE_SESSION_ENGINE') or '')==engine
    parts=[]
    identity=agent_for_dir(where) if where else ''
    if not identity and mine:
        try:identity=clean(json.loads(env.get('WORKSPACE_AGENT_UI') or '{}').get('name') or '')
        except (ValueError,AttributeError):identity=''
    if identity:parts.append(_paint(K,'accent',(K.get('B') or '')+identity))
    if mine:
        tab=clean(env.get('WORKSPACE_WS') or '')[:60]
        if tab:parts.append(_paint(K,'dim',tab))
    return parts,where


def _context_part(pct,ctx,K):
    """«contexto N%» si el motor lo midió; «contexto tras el 1er mensaje» si
    trae el bloque sin medir; None si no trae nada."""
    if pct is not None:
        return _paint(K,'warn' if pct>=80 else 'dim',
                      t('motorbar.context','contexto {pct}%','context {pct}%',pct='%.0f' % pct))
    if ctx:
        return _paint(K,'dim',t('motorbar.context_pending','contexto tras el 1er mensaje',
                                'context after the first message'))
    return None


def _fit(lines,width):
    import hublayout as H
    try:width=max(16,min(1000,int(width)))
    except (TypeError,ValueError):width=100
    return [H.clip(line,width) for line in lines if line]


def git_branch(path,max_up=25):
    """Rama de git de `path` leyendo .git/HEAD (sin procesos: la barra corre
    tras cada evento del motor); sha corto si está desacoplada; '' si no hay."""
    try:
        p=os.path.realpath(str(path or ''))
    except Exception:
        return ''
    for _ in range(max_up):
        if not p:
            break
        g=os.path.join(p,'.git')
        try:
            if os.path.isfile(g):
                with open(g,encoding='utf-8',errors='replace') as fh:
                    first=fh.read(4096).strip()
                if not first.startswith('gitdir:'):
                    return ''
                g=first.split(':',1)[1].strip()
                if not os.path.isabs(g):
                    g=os.path.join(p,g)
            if os.path.isdir(g):
                with open(os.path.join(g,'HEAD'),encoding='utf-8',errors='replace') as fh:
                    head=fh.read(512).strip()
                if head.startswith('ref:'):
                    ref=head.split(':',1)[1].strip()
                    return clean(ref[len('refs/heads/'):] if ref.startswith('refs/heads/') else ref)[:60]
                return clean(head[:7])
        except OSError:
            return ''
        parent=os.path.dirname(p)
        if parent==p:
            break
        p=parent
    return ''


def copilot_lines(payload,color=None,env=None,width=100):
    """La barra de Workspace en GitHub Copilot (su statusLine nativa, se APILA
    bajo su pie; ver motor_statusline). UNA línea: agente · pestaña · modelo ·
    contexto · uso de la sesión (créditos IA o solicitudes premium) · líneas
    cambiadas · «todo permitido» · versión del cerebro. Solo lo que Copilot
    publica en el JSON: lo que no está o no se midió se omite o se dice
    («contexto tras el 1er mensaje»), jamás un 0 inventado. La cuota del plan
    no viene en el JSON: la pinta el pie nativo. `color=None` → terminal."""
    env=os.environ if env is None else env
    K=colors(color)
    model,ctx,cost,ai=_dict(payload,'model'),_dict(payload,'context_window'),_dict(payload,'cost'),_dict(payload,'ai_used')
    parts,where=_identity(payload,env,'copilot',K)
    name=clean(model.get('display_name') or model.get('id') or '')[:80]
    if name:parts.append(_paint(K,'text',name))
    part=_context_part(_copilot_context(ctx),ctx,K)
    if part:parts.append(part)
    nano=_num(ai.get('total_nano_aiu'))
    shown=clean(ai.get('formatted') or '')[:20]
    premium=_num(cost.get('total_premium_requests'))
    if nano and shown:
        parts.append(_paint(K,'dim',t('motorbar.copilot.ai_used','{n} créditos IA','{n} AI credits',n=shown)))
    elif premium:
        parts.append(_paint(K,'dim',t('motorbar.copilot.premium','{n} solicitudes premium',
                                      '{n} premium requests',n='%g' % premium)))
    added,removed=_num(cost.get('total_lines_added')),_num(cost.get('total_lines_removed'))
    if added or removed:            # el que no vino no se pinta: desconocido ≠ 0
        lines=(['+%d' % int(added)] if added is not None else [])+(['-%d' % int(removed)] if removed is not None else [])
        parts.append(_paint(K,'dim',' '.join(lines)))
    if payload.get('allow_all_enabled') is True:
        parts.append(_paint(K,'warn',t('motorbar.copilot.allow_all','todo permitido','all allowed')))
    version=brain_version(where) if where else ''
    if version:parts.append(_paint(K,'dim',version))
    if not parts:return []
    return _fit([_paint(K,'dim',' · ').join(parts)],width)


def cursor_lines(payload,color=None,env=None,width=100,workspace=False):
    """La barra de Workspace en Cursor (su statusLine nativa REEMPLAZA la fila
    del pie: modelo · % de tokens · carpeta · rama; ver motor_statusline).
    Primera línea: agente · pestaña · modelo (+ parámetros, MAX) · contexto ·
    auto-run · modo vim · versión del cerebro. Fuera de una sesión de
    Workspace, segunda línea con la carpeta · rama (lo que la fila nativa
    mostraba). Siempre imprime algo: vacía, Cursor dejaría la fila en blanco.
    Solo lo que el JSON trae: el % es null hasta medir → «tras el 1er
    mensaje»; los archivos editados no vienen en el JSON y no se inventan."""
    env=os.environ if env is None else env
    K=colors(color)
    model,ctx,vim=_dict(payload,'model'),_dict(payload,'context_window'),_dict(payload,'vim')
    parts,where=_identity(payload,env,'cursor',K)
    name=clean(model.get('display_name') or model.get('id') or '')[:80]
    if name:
        extra=clean(model.get('param_summary') or '')[:40]
        # Cursor 2026.10.22 ya trae los parámetros en display_name («Grok 4.7
        # 256K High Fast» + param_summary «256K High Fast», visto en vivo):
        # sumarlos otra vez los repetía en la barra.
        if extra and extra.lower() not in name.lower():name+=' '+extra
        if model.get('max_mode') is True:name+=' · MAX'
        parts.append(_paint(K,'text',name))
    pct=_num(ctx.get('used_percentage'))
    part=_context_part(pct if pct is not None and pct<=100 else None,ctx,K)
    if part:parts.append(part)
    if payload.get('autorun') is True:
        parts.append(_paint(K,'warn',t('motorbar.cursor.autorun','auto-run','auto-run')))
    mode=clean(vim.get('mode') or '').upper()[:12]
    if mode and mode!='NORMAL':parts.append(_paint(K,'dim','-- %s --' % mode))
    version=brain_version(where) if (where and workspace) else ''
    if version:parts.append(_paint(K,'dim',version))
    lines=[_paint(K,'dim',' · ').join(parts) if parts else _paint(K,'dim','Cursor')]
    if not workspace:
        cwd=str(payload.get('cwd') or _dict(payload,'workspace').get('current_dir') or '')
        if cwd:
            home=os.path.expanduser('~')
            shown=('~'+cwd[len(home):]) if home and home!='/' and (cwd==home or cwd.startswith(home+os.sep)) else cwd
            branch=git_branch(cwd)
            lines.append(_paint(K,'dim',clean(shown)+(' · '+branch if branch else '')))
    return _fit(lines,width)
