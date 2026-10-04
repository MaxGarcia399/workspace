"""Isolated tmux footer around the official CLI; never sends model requests."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import workspace_status as S

def footer(meta,now=None,width=160):
    from engines.codex import rate_limit_snapshot
    now=time.time() if now is None else now
    first=' · '.join(filter(None,[S.clean(meta['agent']),'Codex',S.brain_version(meta['brain']),
                                  'activa '+S.duration(now-meta['started'])]))
    snap=rate_limit_snapshot()
    rows=[]
    if snap:
        for key,label in (('primary','5h'),('secondary','Semanal')):
            item=snap.get(key)
            if isinstance(item,dict):
                text=S.window(label,item.get('used_percent'),item.get('resets_at'),now)
                if width < 160:
                    import re
                    text=re.sub(r' [█░]+ ', ' ', text).replace('reinicia ','↻ ').replace('Semanal','Semana')
                rows.append(text)
        if snap.get('at'):rows.append(('lectura hace ' if width >= 160 else 'datos ')+S.duration(now-snap['at']))
    return [first,'  │  '.join(rows) if rows else 'Cuotas: esperando datos de Codex']

def tmux_quote(value):
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'

def run(argv,cfg,env=None):
    if os.name!='posix' or os.environ.get('TMUX') or not sys.stdin.isatty() or not shutil.which('tmux') or os.environ.get('WORKSPACE_CODEX_NO_LIVE_BAR')=='1':
        return subprocess.call(argv,cwd=cfg['_brain'],env=env)
    # Unique socket isolates this footer from user tmux sessions/preferences.
    with tempfile.TemporaryDirectory(prefix='workspace-codex-status-') as tmp:
        root=Path(tmp);meta=root/'session.json';result=root/'exit.json'
        meta.write_text(json.dumps({'agent':cfg.get('display') or cfg.get('name','Agente'),
                                   'brain':cfg['_brain'],'started':time.time(),'argv':argv,'result':str(result)}))
        os.chmod(meta,0o600)
        script=str(Path(__file__).resolve());python=sys.executable
        status=[shlex.join([python,script,'--footer',str(meta),str(i),'#{client_width}']) for i in range(2)]
        config=root/'tmux.conf'
        config.write_text('\n'.join(['set -g status 2','set -g status-interval 5',
          'set -g status-style bg=default,fg=default','set -g status-left ""','set -g status-right ""',
          'set -g prefix None','set -g mouse off','set -g allow-passthrough on',
          'set -g default-terminal "tmux-256color"',
          'set -g status-format[0] '+tmux_quote('#('+status[0]+')'),
          'set -g status-format[1] '+tmux_quote('#('+status[1]+')')])+'\n')
        socket='workspace-status-'+uuid.uuid4().hex
        command=shlex.join([python,script,'--child',str(meta)])
        try:
            rc=subprocess.call(['tmux','-L',socket,'-f',str(config),'new-session','-s','codex','-c',cfg['_brain'],command],env=env)
            if result.exists():
                return int(json.loads(result.read_text()))
            if rc and not result.with_suffix('.started').exists():
                subprocess.run(['tmux','-L',socket,'kill-server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return subprocess.call(argv,cwd=cfg['_brain'],env=env)
            return rc or 1
        finally:
            subprocess.run(['tmux','-L',socket,'kill-server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    mode,path=sys.argv[1:3];meta=json.loads(Path(path).read_text())
    if mode=='--child':
        Path(meta['result']).with_suffix('.started').touch()
        rc=subprocess.call(meta['argv'],cwd=meta['brain'])
        Path(meta['result']).write_text(json.dumps(rc))
        return rc
    if mode=='--footer':
        try:
            width=int(sys.argv[4]) if len(sys.argv)>4 else 160
            print(footer(meta,width=width)[int(sys.argv[3])])
        except Exception:print('Workspace · cuota sin datos')
        return 0
    return 1

if __name__=='__main__':sys.exit(main())
