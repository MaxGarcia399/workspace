"""Isolated tmux footer around the official CLI; never sends model requests.

UNA SOLA BARRA (plan motores 2026-10-13): la barra de Codex es la NATIVA
(`-c tui.status_line=[…]`, ver engines/codex.py). Este pie de Workspace (2
líneas en un tmux aislado) es OPT-IN con WORKSPACE_CODEX_LIVE_BAR=1; cuando
de verdad corre, la nativa se apaga para esa corrida (`-c tui.status_line=[]`)
y queda una sola barra. La decisión «¿corre el pie?» vive en UNA función,
`footer_enabled()`, que usan el lanzador y el armado del argv — así jamás se
apaga la nativa sin que el pie exista (cliente sin tmux = barra nativa).
"""
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

#: Opt-in del pie de tmux (antes era el default y doblaba la barra).
LIVE_BAR_ENV = 'WORKSPACE_CODEX_LIVE_BAR'
#: Kill-switch histórico: sigue ganando sobre el opt-in.
NO_LIVE_BAR_ENV = 'WORKSPACE_CODEX_NO_LIVE_BAR'
_STATUS_KEY = 'tui.status_line='


def footer_enabled():
    """¿Corre el pie de Workspace en ESTA corrida? Opt-in explícito
    (WORKSPACE_CODEX_LIVE_BAR=1) + POSIX + fuera de tmux + con tty + tmux en
    el PATH, y sin el kill-switch. Fuente ÚNICA para run() y para el argv."""
    if os.environ.get(NO_LIVE_BAR_ENV) == '1':
        return False
    if str(os.environ.get(LIVE_BAR_ENV, '')).strip().lower() not in ('1', 'true', 'yes', 'on', 'si', 'sí'):
        return False
    try:
        tty = sys.stdin.isatty()
    except Exception:
        tty = False
    return os.name == 'posix' and not os.environ.get('TMUX') and tty and bool(shutil.which('tmux'))


def footer_argv(argv):
    """argv con la barra NATIVA apagada (`-c tui.status_line=[]`) para cuando
    el pie corre: reemplaza el override de status line que ya traiga, o lo
    inserta antes de `-s` (después de `codex [resume <id>]`)."""
    out = list(argv)
    for i, a in enumerate(out):
        s = str(a)
        if s.replace(' ', '').startswith(_STATUS_KEY) and i > 0 and out[i - 1] == '-c':
            out[i] = _STATUS_KEY + '[]'
            return out
        if s.replace(' ', '').startswith('-c' + _STATUS_KEY):
            out[i] = '-c' + _STATUS_KEY + '[]'
            return out
    at = out.index('-s') if '-s' in out else min(1, len(out))
    return out[:at] + ['-c', _STATUS_KEY + '[]'] + out[at:]


def footer(meta,now=None,width=160):
    from engines.codex import rate_limit_snapshot
    now=time.time() if now is None else now
    first=' · '.join(filter(None,[S.clean(meta['agent']),'Codex',S.brain_version(meta['brain']),
                                  S.t('motorbar.active','activa {d}','up {d}',d=S.duration(now-meta['started']))]))
    snap=rate_limit_snapshot()
    rows=[]
    if snap:
        for key,label in (('primary','5h'),('secondary',S.t('motorbar.weekly','Semanal','Weekly'))):
            item=snap.get(key)
            if isinstance(item,dict):
                # Reinicio YA pasado → la ventana se reinició desde la última
                # lectura: el % viejo no vale (antes: «reinicio pendiente de
                # confirmar» con el número muerto).
                text=S.window(label,item.get('used_percent'),item.get('resets_at'),now,
                              reset_passed=S.t('motorbar.reset_done','ventana reiniciada','window reset'))
                if width < 160:
                    import re
                    text=re.sub(r' [█░]+ ', ' ', text).replace(S.t('motorbar.resets_word','reinicia ','resets in '),'↻ ')
                rows.append(text)
        if snap.get('at'):rows.append((S.t('motorbar.read_ago','lectura hace {d}','read {d} ago',d=S.duration(now-snap['at']))
                                       if width >= 160 else S.t('motorbar.data_ago','datos {d}','data {d}',d=S.duration(now-snap['at']))))
    return [first,'  │  '.join(rows) if rows else S.t('motorbar.codex_waiting','Cuotas: esperando datos de Codex','Quotas: waiting for Codex data')]

def tmux_quote(value):
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'

def run(argv,cfg,env=None):
    if not footer_enabled():
        return subprocess.call(argv,cwd=cfg['_brain'],env=env)
    # Unique socket isolates this footer from user tmux sessions/preferences.
    with tempfile.TemporaryDirectory(prefix='workspace-codex-status-') as tmp:
        root=Path(tmp);meta=root/'session.json';result=root/'exit.json'
        meta.write_text(json.dumps({'agent':cfg.get('display') or cfg.get('name','Agente'),
                                   'brain':cfg['_brain'],'started':time.time(),'argv':footer_argv(argv),'result':str(result)}), encoding="utf-8")
        os.chmod(meta,0o600)
        script=str(Path(__file__).resolve());python=sys.executable
        status=[shlex.join([python,script,'--footer',str(meta),str(i),'#{client_width}']) for i in range(2)]
        config=root/'tmux.conf'
        config.write_text('\n'.join(['set -g status 2','set -g status-interval 5',
          'set -g destroy-unattached on',
          'set -g status-style bg=default,fg=default','set -g status-left ""','set -g status-right ""',
          'set -g prefix None','set -g mouse off','set -g allow-passthrough on',
          'set -g default-terminal "tmux-256color"',
          'set -g status-format[0] '+tmux_quote('#('+status[0]+')'),
          'set -g status-format[1] '+tmux_quote('#('+status[1]+')')])+'\n', encoding="utf-8")
        socket='workspace-status-'+uuid.uuid4().hex
        command=shlex.join([python,script,'--child',str(meta)])
        try:
            rc=subprocess.call(['tmux','-L',socket,'-f',str(config),'new-session','-s','codex','-c',cfg['_brain'],command],env=env)
            if result.exists():
                return int(json.loads(result.read_text(encoding="utf-8")))
            if rc and not result.with_suffix('.started').exists():
                # El pie no llegó a arrancar: corre el CLI con SU barra nativa
                # (argv original, sin el status_line=[] del pie).
                subprocess.run(['tmux','-L',socket,'kill-server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return subprocess.call(argv,cwd=cfg['_brain'],env=env)
            return rc or 1
        finally:
            subprocess.run(['tmux','-L',socket,'kill-server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    mode,path=sys.argv[1:3];meta=json.loads(Path(path).read_text(encoding="utf-8"))
    if mode=='--child':
        Path(meta['result']).with_suffix('.started').touch()
        rc=subprocess.call(meta['argv'],cwd=meta['brain'])
        Path(meta['result']).write_text(json.dumps(rc), encoding="utf-8")
        return rc
    if mode=='--footer':
        try:
            width=int(sys.argv[4]) if len(sys.argv)>4 else 160
            print(footer(meta,width=width)[int(sys.argv[3])])
        except Exception:print(S.t('motorbar.footer_nodata','Workspace · cuota sin datos','Workspace · no quota data'))
        return 0
    return 1

if __name__=='__main__':sys.exit(main())
