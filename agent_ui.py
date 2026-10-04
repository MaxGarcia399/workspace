"""WORKSPACE · agent_ui — greeter/picker CANÓNICO de los agentes.

ÚNICA fuente del formato del greeter (banner/heading centrado + caja
«SESIONES · ↑↓ elige · Enter abre» centrada y COMPACTA). Los dashboards de
agentes (repo `agents/*/brand/`, cerebros `<BRAIN>/brand/` y el template
`templates/agent/workspace/brand/agent-dashboard.py`) DELEGAN aquí su
`run_picker` → todos se ven idénticos y un agente nuevo (creado desde el
template) hereda el formato sin copiar render. No dupliques este render en
un dashboard: si falta algo, se agrega AQUÍ."""
import ast
import functools
from pathlib import Path
import shutil
import os
import hublayout as H
import responsive_ui as UI
import tuitheme

@functools.lru_cache(maxsize=1)
def font():
    tree = ast.parse((Path(__file__).parent / 'templates/agent/workspace/brand/agent-banner.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'FONT' for t in node.targets):
            return ast.literal_eval(node.value)
    return {}

def heading(name, tagline, cols):
    p = tuitheme.palette()
    glyphs = [font().get(c, font()[' ']) for c in name.upper()]
    rows = [''.join(g[i] for g in glyphs) for i in range(6)]
    width = max(map(H.vis, rows), default=0)
    if width > cols - 5:
        rows = [p.C + p.BO + name.upper() + p.R]
    else:
        rows = [H._neon_row(row, p.WCOL[i % len(p.WCOL)] + p.BO, p.B2, p.R) for i,row in enumerate(rows)]
    lines = [''] + [' ' * max(0,(cols-1-H.vis(row))//2) + row for row in rows]
    if tagline:
        text = H.clip(tagline, cols-5)
        lines += ['', ' ' * max(0,(cols-1-H.vis(text))//2) + p.DIM + text + p.R]
    return lines + ['']

def picker_frame(items, selected, width, height, box_w=None, left=None):
    """Caja de sesiones: nombre a la IZQUIERDA y estado alineado al borde
    DERECHO del cuadro (la caja ancha se aprovecha completa), título
    CENTRADO en el marco, caja CENTRADA. Es EL formato del picker para
    todos los agentes. `box_w`/`left` (los pasa session_screen) ALINEAN la
    caja con la del banner: MISMO ancho y MISMO borde izquierdo → los dos
    marcos quedan apilados como un bloque único."""
    cap = max(1,height-20)
    start = max(0,min(selected-cap//2,len(items)-cap))
    lw = min(max([H.vis(l) for l,_,_ in items] + [8]), 28)   # col. nombre
    sw = min(max([H.vis(s) for _,s,_ in items] + [0]), 26)   # col. estado
    # 40 col = cabe el título entero; el límite de la terminal SIEMPRE gana
    # (en ventanas angostas UI.box recorta el título, jamás rompe el marco).
    pw = max(8, min(max(40, lw + sw + 11), width - 5))
    if box_w:
        # heredar el ANCHO de la caja del banner (sin exceder la terminal
        # ni encoger por debajo del contenido compacto mínimo)
        pw = max(pw, min(int(box_w), width - 5))
    inner = pw - 4                               # ancho útil entre bordes
    body=[]
    for i,(label,sub,_) in enumerate(items):
        if start <= i < start+cap:
            row = ('> ' if i == selected else '  ') \
                + H.clip(label, max(1, inner - 10))
            sub_c = H.clip(sub, max(0, inner - H.vis(row) - 2))
            gap = max(2, inner - H.vis(row) - H.vis(sub_c))
            body.append(row + ' ' * gap + sub_c)   # estado pegado al borde →
    if start:
        body.insert(0,'↑ más sesiones')
    if start+cap < len(items):
        body.append('↓ más sesiones')
    if left is None or not box_w or pw != int(box_w):
        left = max(0, (width - 1 - pw) // 2)     # centrada a la terminal
    return [' '*left+x for x in UI.box('SESIONES · ↑↓ elige · Enter abre',
                                       body,pw,True,title_align='center')]

def draw_picker(out, items, selected, state):
    try:
        ts = os.get_terminal_size(out.fileno())
    except (OSError, AttributeError, ValueError):
        ts = shutil.get_terminal_size((80,54))
    lines = picker_frame(items,selected,ts.columns,ts.lines)
    if state.get('rows'):
        out.write('\033[%dA' % state['rows'])
    for line in lines:
        out.write('\r\033[K'+line+'\r\n')
    out.write('\033[J')
    out.flush()
    state['rows']=len(lines)


def export_context(cfg):
    import json
    os.environ['WORKSPACE_AGENT_UI'] = json.dumps({
        'name': cfg.get('display') or cfg.get('name','Agente'),
        'tagline': cfg.get('tagline',''),
        'banner': (cfg.get('_scripts') or {}).get('banner','')})

def session_screen(items, selected, width, height, context, banner=''):
    # Keep a full illustration only when both dimensions allow the picker.
    illustrated = banner.splitlines()
    bw = max(map(H.vis,illustrated),default=0)
    box_w = box_left = None
    if illustrated and bw < width and len(illustrated) <= height-12:
        box_left = max(0, (width - 1 - bw) // 2)     # banner CENTRADO
        pad = ' ' * box_left
        top = [pad + ln if ln.strip() else ln for ln in illustrated] + ['']
        box_w = bw        # la caja SESIONES hereda ancho+margen del banner:
                          # los dos marcos quedan ALINEADOS (bloque único)
    else:
        top = heading(context['name'],context.get('tagline',''),width)
    spare = max(1,height-1-len(top)-4)
    rows = picker_frame(items,selected,width,spare+20,box_w=box_w,left=box_left)
    return [H.clip(x,width-1) for x in (top+rows)[:height-1]]

def _apply_theme_osc(palette):
    """Fondo/tinta del TEMA activo — paridad EXACTA con el hub (front.py):
    un tema no-default trae su propio fondo (tui.osc en themes/<id>/
    theme.json); sin OSC (olympo/mono) se RESTAURA el fondo legacy
    'workspace'. Sin el else, al volver de un tema oscuro el fondo viejo se
    quedaba pegado en el picker (gap del cambio de tema en vivo)."""
    import theme
    if getattr(palette, 'OSC', None):
        theme.apply_colors(palette.OSC)
    else:
        theme.apply('workspace')


def live_picker(items, script):
    """TTY picker with idle theme/size refresh and an unchanged selected row."""
    import json, time, subprocess, sys
    try:
        if sys.platform == 'win32':
            import msvcrt
            inp, out = sys.stdin, open('CONOUT$','w',encoding='utf-8')
        else:
            import termios, tty, select
            inp, out = open('/dev/tty','rb',buffering=0), open('/dev/tty','w')
    except OSError:
        return None
    if not items:
        inp.close(); out.close()
        return None
    context = json.loads(os.environ.get('WORKSPACE_AGENT_UI','{}'))
    context.setdefault('name',Path(script).stem.replace('-dashboard','').capitalize())
    selected, signature, banner = 0, None, ''
    redraw = True
    old = None
    try:
        if sys.platform != 'win32':
            old = termios.tcgetattr(inp.fileno())
            tty.setraw(inp.fileno())
        while True:
            try:
                size = os.get_terminal_size(out.fileno())
            except OSError:
                size = shutil.get_terminal_size((80,54))
            palette = tuitheme.palette()
            current = (palette.id,palette.mode,size.columns,size.lines)
            if current != signature:
                if context.get('banner'):
                    result = subprocess.run([sys.executable,context['banner']],capture_output=True,text=True,encoding='utf-8',errors='replace')
                    banner = result.stdout if result.returncode == 0 else ''
                # Tema EN VIVO — MISMO mecanismo que el hub (front.py): el
                # tick de 0.2s re-resuelve tuitheme.palette() (env/settings
                # se releen de disco en cada get) y aquí se repinta todo.
                _apply_theme_osc(palette)
            if current != signature or redraw:
                UI.paint(out,session_screen(items,selected,size.columns,size.lines,context,banner),first=signature is None)
                signature = current
            redraw = False
            if sys.platform == 'win32':
                if not msvcrt.kbhit():
                    time.sleep(.2); continue
                key = msvcrt.getwch()
                if key in ('\x00','\xe0'):
                    key = {'H':'up','P':'down'}.get(msvcrt.getwch(),'')
            else:
                if not select.select([inp],[],[],.2)[0]:
                    continue
                key = os.read(inp.fileno(),1).decode('ascii',errors='ignore')
                if key == '\x1b' and select.select([inp],[],[],.05)[0]:
                    second = os.read(inp.fileno(),1)
                    if second in (b'[',b'O') and select.select([inp],[],[],.05)[0]:
                        key = {b'A':'up',b'B':'down'}.get(os.read(inp.fileno(),1),'')
            if key in ('\r','\n'):
                return selected
            if key == '\x03':
                return len(items)-1
            if key == 'up':
                selected = (selected-1)%len(items)
            elif key == 'down':
                selected = (selected+1)%len(items)
            elif key in '123456789' and key and int(key) <= len(items):
                return int(key)-1
            else:
                continue
            redraw = True
    finally:
        if old is not None:
            termios.tcsetattr(inp.fileno(),termios.TCSADRAIN,old)
        if sys.platform != 'win32':
            inp.close()
        out.close()
