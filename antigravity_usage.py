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


def shim_path(home=None,name=SHIM_NAME):
    return Path(home or Path.home())/'.local'/'bin'/name


def shim_text(root=None,python=None,script='antigravity_usage.py',mark=_SHIM_MARK,motor='Antigravity',args=()):
    """Script POSIX del shim (sh). Bake: raíz del harness y Python actuales,
    como respaldo de $WORKSPACE_ROOT / python3 del PATH. Siempre sale con 0
    (una barra rota jamás debe ensuciar la UI del motor). `script`/`mark`/
    `motor`/`args`: el mismo shim sirve a otras statusLine nativas
    (motor_statusline: Copilot, Cursor); con los defaults sale idéntico al de
    siempre."""
    import re
    import shlex
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.py',script): raise ValueError('script')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+',str(a)) for a in args): raise ValueError('args')
    root=str(root or Path(__file__).resolve().parent)
    python=str(python or sys.executable or 'python3')
    return '\n'.join([
        '#!/bin/sh',
        mark+' (generado; se reescribe al abrir un agente en %s).' % motor,
        'root="${WORKSPACE_ROOT:-}"',
        '[ -n "$root" ] && [ -f "$root/%s" ] || root=%s' % (script,shlex.quote(root)),
        'if [ ! -f "$root/%s" ]; then cat >/dev/null; exit 0; fi' % script,
        'py=%s' % shlex.quote(python),
        '[ -x "$py" ] || py="$(command -v python3 2>/dev/null)"',
        'if [ -z "$py" ]; then cat >/dev/null; exit 0; fi',
        '"$py" "$root/%s"%s || true' % (script,''.join(' '+str(a) for a in args)),
        'exit 0',''])


def ensure_shim(home=None,name=SHIM_NAME,text=None,mark=_SHIM_MARK):
    """Escribe/actualiza el shim (solo POSIX). Devuelve su ruta o None. No
    pisa un archivo con ese nombre que no sea nuestro (sin `mark`)."""
    if os.name=='nt': return None
    p=shim_path(home,name)
    try:
        if p.is_symlink(): return None
        want=shim_text() if text is None else text
        if p.exists():
            cur=p.read_text(encoding='utf-8',errors='replace')
            if mark not in cur: return None
            if cur==want:
                if not os.access(str(p),os.X_OK): os.chmod(str(p),0o755)
                return p
        p.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.'+name+'-',dir=str(p.parent))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(want)
            os.chmod(tmp,0o755)
            os.replace(tmp,str(p))
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return p
    except OSError: return None


# Windows: agy y Cursor corren la statusLine con cmd.exe, y una ruta con
# espacios entre comillas la rompe. VERIFICADO 2026-11-06 en caja negra
# (Windows 11, agy 1.5.2 y cursor-agent 2026.11.05, usuario y Workspace en
# carpetas con espacios):
#   · la sonda `echo %ComSpec% $($PSVersionTable.PSVersion)` pinta
#     `C:\Windows\system32\cmd.exe` y el `$(…)` literal: es cmd, no PowerShell;
#   · `"…\python.exe" "…\antigravity_usage.py"`: agy escapa cada comilla como
#     `\"` y cmd responde «"\"C:\…\python.exe\"" no se reconoce como un
#     comando…» (a las 30 fallas la apaga); Cursor no pinta nada (ni error);
#   · anteponer `call ` falla igual en los dos;
#   · SIN comillas, con los nombres cortos 8.3, se pinta en los dos.
# Por eso, en Windows, una CARPETA con espacios va con su nombre corto 8.3
# (GetShortPathNameW) y el archivo con su nombre largo: is_ours y el
# desinstalador reconocen la barra por él. Sin nombres 8.3 en ese disco, va
# entre comillas como antes. Una ruta sin espacios no cambia.
def win_cmdline(partes):
    """Línea de comandos de la statusLine en Windows SIN comillas cuando se
    puede (ver arriba): cada parte con espacios pasa a carpeta corta 8.3 +
    nombre largo; si no hay nombre corto, list2cmdline la entrecomilla."""
    out=[]
    for p in partes:
        p=str(p)
        if ' ' in p or '\t' in p:
            carpeta,nombre=os.path.split(p)
            corta=_ruta_corta(carpeta)
            if corta and nombre and not any(c in corta+nombre for c in ' \t"'):
                p=corta.rstrip('\\')+'\\'+nombre
        out.append(p)
    return subprocess.list2cmdline(out)


def _ruta_corta(path):
    """Nombre corto 8.3 de `path` (Windows; debe existir) o '' si no hay."""
    if os.name!='nt' or not path: return ''
    try:
        import ctypes
        f=ctypes.windll.kernel32.GetShortPathNameW
        n=f(str(path),None,0)
        if not n: return ''
        buf=ctypes.create_unicode_buffer(n)
        return buf.value if f(str(path),buf,n) else ''
    except Exception: return ''


def bridge_config(home=None):
    """statusLine que Workspace quiere: el shim (POSIX) o, en Windows / sin
    shim, Python + este archivo (win_cmdline: sin comillas si se puede)."""
    shim=ensure_shim(home)
    if shim is not None:
        command=__import__('shlex').join([str(shim)])
    else:
        command=win_cmdline([sys.executable,str(Path(__file__).resolve())]) if os.name=='nt' else __import__('shlex').join([sys.executable,str(Path(__file__).resolve())])
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
        # the single reader (_utf8): BYTES → UTF-8 with BOM tolerated. Read as
        # text, Windows decoded agy's payload as cp1252 and an accented path
        # broke it. Over MAX_BYTES, garbage or a non-object → {} → no bar.
        import _utf8
        data=_utf8.json_de_stdin(limite=MAX_BYTES)
        if not data: return
        snap=snapshot(data)
        if snap: _atomic(cache_path(),snap)
        from workspace_status import antigravity_lines
        print('\n'.join(antigravity_lines(data)))
    except Exception:
        pass
    # Only formatted status text goes to stdout; never diagnostics or auth.


if __name__=='__main__': main()
