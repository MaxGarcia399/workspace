"""Antigravity official statusline quota bridge. No credentials or model calls.

Schema: https://antigravity.google/docs/cli/statusline . The native statusline
remains visible (stack_with_default). Only quota/model/plan and observation time
are cached; incoming email, transcript paths, prompts and auth are discarded.
"""
import datetime
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

MAX_BYTES=65536


def cache_path():
    return Path.home()/'.claude/workspace/antigravity-usage.json'


def _stamp(value):
    if isinstance(value,(int,float)):
        result=float(value)
    else:
        result=datetime.datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    if not math.isfinite(result) or not 0<result<100_000_000_000:
        raise ValueError('Invalid reset')
    return result


def snapshot(payload, observed=None):
    now=time.time() if observed is None else observed
    buckets=[]
    quotas=payload.get('quota')
    if not isinstance(quotas,dict): return None
    for name,window in list(quotas.items())[:32]:
        if not isinstance(window,dict) or not isinstance(name,str): continue
        try:
            raw=window['remaining_fraction']
            if isinstance(raw,bool): continue
            free=float(raw)
            if not math.isfinite(free) or not 0<=free<=1: continue
            reset=None
            if window.get('reset_time'):
                reset=_stamp(window['reset_time'])
            elif window.get('reset_in_seconds') is not None:
                seconds=float(window['reset_in_seconds'])
                if not math.isfinite(seconds) or not 0<=seconds<=31536000: continue
                reset=now+seconds
            label=' '.join(name.split())[:80]
            if not label or any(ord(c)<32 or ord(c)==127 for c in name): continue
            buckets.append({'label':label,'used_percent':(1-free)*100,'resets_at':reset})
        except (KeyError,ValueError,TypeError,OverflowError): continue
    if not buckets: return None
    model=payload.get('model') or {}
    return {'at':now,'buckets':buckets,'model':str(model.get('id') or '')[:120] if isinstance(model,dict) else '',
            'plan_type':str(payload.get('plan_tier') or '')[:80],'source':'Antigravity statusline'}


def _atomic(path, data):
    path=Path(path)
    if path.is_symlink(): raise ValueError('Symlink destination')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.agy-quota-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def read_snapshot(path=None):
    try:
        p=Path(path or cache_path())
        if p.is_symlink() or p.stat().st_size>MAX_BYTES: return None
        value=json.loads(p.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) and value.get('source')=='Antigravity statusline' else None
    except (OSError,ValueError,TypeError): return None


def bridge_config():
    command=subprocess.list2cmdline([sys.executable,str(Path(__file__).resolve())]) if os.name=='nt' else __import__('shlex').join([sys.executable,str(Path(__file__).resolve())])
    return {'type':'command','command':command,'stack_with_default':True}


def ensure_statusline(settings_path=None):
    """Wire on launch, preserving an existing custom/disabled statusline.

    Returns a status for the preferences menu; never executes user commands.
    """
    path=Path(settings_path or Path.home()/'.gemini/antigravity-cli/settings.json')
    if path.is_symlink(): return 'blocked'
    try:
        if path.exists():
            if path.stat().st_size>1024*1024: return 'blocked'
            data=json.loads(path.read_text(encoding='utf-8'))
        else: data={}
        if not isinstance(data,dict): return 'blocked'
        existing=data.get('statusLine')
        if 'statusLine' in data:
            return 'ready' if isinstance(existing,dict) and existing.get('command')==bridge_config()['command'] and existing.get('enabled',True) else 'custom'
        data['statusLine']=bridge_config()
        if path.exists():
            backup=path.with_name('settings.workspace-quota-backup.json')
            if not backup.exists(): _atomic(backup,json.loads(path.read_text(encoding='utf-8')))
        _atomic(path,data)
        return 'ready'
    except (OSError,ValueError,TypeError,AttributeError): return 'blocked'


def main():
    try:
        raw=sys.stdin.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: return
        data=json.loads(raw)
        snap=snapshot(data) if isinstance(data,dict) else None
        if snap: _atomic(cache_path(),snap)
        if isinstance(data,dict):
            from workspace_status import antigravity_lines
            print('\n'.join(antigravity_lines(data)))
    except Exception:
        pass
    # Only formatted status text goes to stdout; never diagnostics or auth.


if __name__=='__main__': main()
