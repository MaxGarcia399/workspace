"""Antigravity official statusline quota bridge. No credentials or model calls.

Schema: https://antigravity.google/docs/cli/statusline . The native statusline
remains visible (stack_with_default). Only quota/model/plan and observation time
are cached; incoming email, transcript paths, prompts and auth are discarded.
Output: workspace_status.antigravity_lines (agent from the payload's
workspace.project_dir/cwd, hub-palette ANSI colors).
"""
import datetime
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
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
    return Path(_paths.state_dir(str(Path.home())))/'antigravity-usage.json'


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


# ── statusLine de agy → shim ESTABLE de Workspace ─────────────────────────────
# Antes la statusLine apuntaba a la RUTA del harness (`python …/antigravity_
# usage.py`); al mover/reinstalar el harness quedaba muerta (agy: «statusline
# command failed exit 2») y, como cualquier statusLine existente se trataba
# como del socio, nunca se reparaba. Ahora apunta a un shim estable,
# ~/.local/bin/workspace-agy-statusline, que resuelve el harness AL CORRER
# ($WORKSPACE_ROOT si agy se abrió desde Workspace; si no, la ruta con que se
# generó, que se reescribe en cada arranque). Una statusLine que mencione
# antigravity_usage.py o el shim es NUESTRA (vieja o rota) → se repara; otra
# cualquiera es del socio → no se toca; una nuestra desactivada → se respeta.
SHIM_NAME='workspace-agy-statusline'
_SHIM_MARK='# WORKSPACE · statusLine de Antigravity'


def shim_path(home=None):
    return Path(home or Path.home())/'.local'/'bin'/SHIM_NAME


def shim_text(root=None,python=None):
    """Script POSIX del shim (sh). Bake: raíz del harness y Python actuales,
    como respaldo de $WORKSPACE_ROOT / python3 del PATH. Siempre sale con 0
    (una barra rota jamás debe ensuciar la UI de agy)."""
    import shlex
    root=str(root or Path(__file__).resolve().parent)
    python=str(python or sys.executable or 'python3')
    return '\n'.join([
        '#!/bin/sh',
        _SHIM_MARK+' (generado; se reescribe al abrir un agente en Antigravity).',
        'root="${WORKSPACE_ROOT:-}"',
        '[ -n "$root" ] && [ -f "$root/antigravity_usage.py" ] || root=%s' % shlex.quote(root),
        'if [ ! -f "$root/antigravity_usage.py" ]; then cat >/dev/null; exit 0; fi',
        'py=%s' % shlex.quote(python),
        '[ -x "$py" ] || py="$(command -v python3 2>/dev/null)"',
        'if [ -z "$py" ]; then cat >/dev/null; exit 0; fi',
        '"$py" "$root/antigravity_usage.py" || true',
        'exit 0',''])


def ensure_shim(home=None):
    """Escribe/actualiza el shim (solo POSIX). Devuelve su ruta o None. No
    pisa un archivo con ese nombre que no sea nuestro."""
    if os.name=='nt': return None
    p=shim_path(home)
    try:
        if p.is_symlink(): return None
        want=shim_text()
        if p.exists():
            cur=p.read_text(encoding='utf-8',errors='replace')
            if _SHIM_MARK not in cur: return None
            if cur==want:
                if not os.access(str(p),os.X_OK): os.chmod(str(p),0o755)
                return p
        p.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.'+SHIM_NAME+'-',dir=str(p.parent))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(want)
            os.chmod(tmp,0o755)
            os.replace(tmp,str(p))
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return p
    except OSError: return None


def bridge_config(home=None):
    """statusLine que Workspace quiere: el shim (POSIX) o, en Windows / sin
    shim, Python + este archivo."""
    shim=ensure_shim(home)
    if shim is not None:
        command=__import__('shlex').join([str(shim)])
    else:
        command=subprocess.list2cmdline([sys.executable,str(Path(__file__).resolve())]) if os.name=='nt' else __import__('shlex').join([sys.executable,str(Path(__file__).resolve())])
    return {'type':'command','command':command,'stack_with_default':True}


def is_ours(command):
    """¿Esta statusLine es de Workspace (actual, vieja o con ruta muerta)?"""
    c=str(command or '')
    return 'antigravity_usage.py' in c or SHIM_NAME in c


#: Estados detallados → los 3 históricos que muestra la UI (agent_create_ui).
_COMPAT={'ready':'ready','repaired':'ready','custom':'custom','off':'custom','blocked':'blocked'}


def ensure_statusline(settings_path=None,home=None,detailed=False):
    """Wire on launch: crea la nuestra, REPARA una nuestra vieja/rota, respeta
    la del socio y una nuestra desactivada. Devuelve 'ready' | 'custom' |
    'blocked' (con detailed=True: 'ready' | 'repaired' | 'custom' | 'off' |
    'blocked'). Nunca ejecuta comandos del socio."""
    st=_ensure_statusline(settings_path,home)
    return st if detailed else _COMPAT.get(st,st)


def _ensure_statusline(settings_path=None,home=None):
    path=Path(settings_path or Path(home or Path.home())/'.gemini/antigravity-cli/settings.json')
    if path.is_symlink(): return 'blocked'
    try:
        if path.exists():
            if path.stat().st_size>1024*1024: return 'blocked'
            data=json.loads(path.read_text(encoding='utf-8'))
        else: data={}
        if not isinstance(data,dict): return 'blocked'
        existing=data.get('statusLine')
        want=bridge_config(home)
        if 'statusLine' in data:
            if not isinstance(existing,dict) or not is_ours(existing.get('command')):
                return 'custom'
            if existing.get('enabled',True) is False:
                return 'off'
            if existing.get('command')==want['command']:
                return 'ready'
            fixed=dict(existing);fixed['command']=want['command'];fixed.setdefault('type','command')
            fixed.setdefault('stack_with_default',True)
            data['statusLine']=fixed;status='repaired'
        else:
            data['statusLine']=want;status='ready'
        if path.exists():
            backup=path.with_name('settings.workspace-quota-backup.json')
            if not backup.exists(): _atomic(backup,json.loads(path.read_text(encoding='utf-8')))
        _atomic(path,data)
        return status
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
