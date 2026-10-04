"""Read-only status formatting; countdowns derive from vendor reset timestamps."""
import math
import time
import re
from pathlib import Path

def clean(value):
    return re.sub(r'[\x00-\x1f\x7f]', '', str(value)).replace('#','').strip()

def duration(seconds):
    seconds=max(0,int(seconds))
    d,seconds=divmod(seconds,86400);h,seconds=divmod(seconds,3600);m,_=divmod(seconds,60)
    return ('%dd %dh' % (d,h)) if d else ('%dh %02dm' % (h,m)) if h else '%dm' % m

def window(label,used,reset,now=None):
    now=time.time() if now is None else now
    try:
        used=float(used)
        if not math.isfinite(used) or not 0<=used<=100: raise ValueError()
    except (TypeError,ValueError):return clean(label)+' · cuota sin datos'
    bar='█'*round(used/100*10)+'░'*(10-round(used/100*10))
    result='%s %s %.0f%% usado' % (clean(label),bar,used)
    if reset is not None:
        try:
            reset=float(reset)
            if math.isfinite(reset):
                result += ' · '+('reinicia '+duration(reset-now) if reset>now else 'reinicio pendiente de confirmar')
        except (ValueError,TypeError):pass
    return result

def brain_version(brain):
    try:
        text=(Path(brain)/'STATE/brain-version.md').read_text()[:2000]
        found=re.search(r'v?\d+\.\d+\.\d+',text)
        return 'Brain '+found.group() if found else ''
    except OSError:return ''

def antigravity_lines(payload,now=None):
    import antigravity_usage as A
    now=time.time() if now is None else now
    model=payload.get('model') or {};ctx=payload.get('context_window') or {};vcs=payload.get('vcs') or {}
    title=[clean(model.get('display_name') or model.get('id') or 'Gemini')]
    try:
        pct=float(ctx.get('used_percentage'))
        if math.isfinite(pct) and 0<=pct<=100:title.append('contexto %.0f%%' % pct)
    except (ValueError,TypeError):pass
    if vcs.get('branch'):title.append(clean(vcs['branch'])+(' ± cambios' if vcs.get('dirty') else ''))
    if payload.get('agent_state'):title.append(clean(payload['agent_state']))
    import os,json
    try:
        identity=json.loads(os.environ.get('WORKSPACE_AGENT_UI','{}')).get('name','')
    except ValueError:identity=''
    if identity:title.insert(0,clean(identity))
    version=brain_version(payload.get('cwd') or os.environ.get('WORKSPACE_BRAIN',''))
    if version:title.append(version)
    lines=[' · '.join(title)]
    snap=A.snapshot(payload,now)
    if snap:
        lines += [window(b['label'],b['used_percent'],b['resets_at'],now) for b in snap['buckets']]
    else:lines.append('Cuota: sin datos del proveedor')
    try:width=max(16,min(1000,int(payload.get('terminal_width') or 100)))
    except (TypeError,ValueError):width=100
    import hublayout as H
    return [H.clip(line,width-1) for line in lines]
