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

# i18n (lado cliente): el greeter lo ven los clientes. Import guardado — este
# módulo lo delegan dashboards que corren desde el brand/ del cerebro, donde
# el root del harness podría no estar en sys.path; sin i18n, _t() devuelve el
# español inline (paridad EXACTA con el greeter de siempre).
try:
    import i18n
except Exception:
    i18n = None


def _t(key, es):
    if i18n is None:
        return es
    try:
        s = i18n.t(key)
        return s if s != key else es
    except Exception:
        return es

@functools.lru_cache(maxsize=1)
def font():
    tree = ast.parse((Path(__file__).parent / 'templates/agent/workspace/brand/agent-banner.py').read_text(encoding='utf-8'))
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

def picker_frame(items, selected, width, height, box_w=None, left=None,
                 notice='', title=None, hints=None):
    """Caja de sesiones: nombre a la IZQUIERDA y estado alineado al borde
    DERECHO del cuadro (la caja ancha se aprovecha completa), título
    CENTRADO en el marco, caja CENTRADA. Es EL formato del picker para
    todos los agentes. `box_w`/`left` (los pasa session_screen) ALINEAN la
    caja con la del banner: MISMO ancho y MISMO borde izquierdo → los dos
    marcos quedan apilados como un bloque único. Sesiones v2: `notice` = una
    línea bajo la caja («Archivada … · u para deshacer»), `title` = otro
    título («ARCHIVADAS») y `hints` = los atajos del pie ((tecla, acción), …)
    en lugar de los de siempre."""
    avisos = _lineas_aviso(notice, max(4, width - 3)) if notice else []
    cap = max(1, height - 20 - max(0, len(avisos) - 1))   # el aviso partido no empuja el pie
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
    ptr = H.cols(tuitheme.palette())['PTR']      # el cursor del hub (❯)
    body=[]
    for i,(label,sub,_) in enumerate(items):
        if start <= i < start+cap:
            row = ((ptr + ' ') if i == selected else '  ') \
                + H.clip(label, max(1, inner - 10))
            sub_c = H.clip(sub, max(0, inner - H.vis(row) - 2))
            gap = max(2, inner - H.vis(row) - H.vis(sub_c))
            body.append(row + ' ' * gap + sub_c)   # estado pegado al borde →
    if start:
        body.insert(0, _t('greeter.sessions.more_up', '↑ más sesiones'))
    if start+cap < len(items):
        body.append(_t('greeter.sessions.more_down', '↓ más sesiones'))
    if left is None or not box_w or pw != int(box_w):
        left = max(0, (width - 1 - pw) // 2)     # centrada a la terminal
    rows = [' '*left+x for x in UI.box(title or _t('greeter.sessions.title', 'SESIONES'),
                                       body, pw, True, title_align='center')]
    if avisos:                                   # el aviso de archivar/deshacer
        p = tuitheme.palette()
        for txt in avisos:                       # centrado bajo la caja, sin salirse
            al = left + (pw - H.vis(txt)) // 2   # más ancho que la caja: centrado igual
            rows.append(' '*max(0, min(al, width - 1 - H.vis(txt))) + p.B2 + txt + p.R)
    # los atajos salen del título y bajan AQUÍ, legibles (tecla en acento,
    # acción en gris — H.keyline, el mismo lenguaje de hints de todo el hub)
    if hints:
        # atajos propios (menú con archivar): son más, así que usan el ancho
        # de la terminal, centrados bajo la caja — en la caja compacta de 40
        # columnas `a`/`u` no cabían y nadie los descubría
        hint = H.keyline(H.cols(tuitheme.palette()), tuple(hints), max(10, width - 3))
        if hint:
            hl = left + (pw - H.vis(hint)) // 2
            rows.append(' '*max(0, min(hl, width - 1 - H.vis(hint))) + hint)
        return rows
    hint = H.keyline(H.cols(tuitheme.palette()),
                     (('↑↓', _t('greeter.hint.choose', 'elige')),
                      ('Enter', _t('greeter.hint.open', 'abre')),
                      ('1-9', _t('greeter.hint.direct', 'directo')),
                      ('Esc', _t('greeter.hint.back', 'regresa'))),
                     max(10, pw - 2))
    if hint:
        rows.append(' '*(left + max(0, (pw - H.vis(hint)) // 2)) + hint)
    return rows

def _lineas_aviso(notice, w):
    """El aviso bajo la caja en ≤2 líneas de ≤w columnas (ancho visual: el
    coreano cuenta doble). Lo que va tras el último « · » es CÓMO deshacer
    («u para deshacer»): jamás se recorta. Si todo no cabe en una línea, se
    parte en dos (la acción arriba, el deshacer abajo); si la acción sola
    tampoco cabe, se acorta ella, nunca el deshacer. Usa el ancho de la
    terminal, no el de la caja (la caja compacta mide 40 columnas)."""
    notice = str(notice or '')
    if H.vis(notice) <= w:
        return [notice]
    accion, sep, deshacer = notice.rpartition(' · ')
    if not sep:
        return [H.clip(notice, w)]
    pegado = w - H.vis(sep + deshacer)
    if H.vis(accion) <= w and H.vis(deshacer) <= w:
        return [accion, deshacer]                # dos líneas enteras
    if pegado >= 12:                             # una línea: se acorta la acción
        return [H.clip(accion, pegado) + sep + deshacer]
    return [H.clip(accion, w), H.clip(deshacer, w)]


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

_BOX_TOPS = ("\u256d", "\u250c", "\u2554", "\u250f")    # ╭ ┌ ╔ ┏


def title_only(lines):
    """Del banner del agente, SOLO el título (el wordmark): se corta en la
    primera caja (la de skills/características). Pedido del socio
    2026-10-12: el menú de sesiones lleva el título y la caja de sesiones,
    nada más. Sin caja → el banner tal cual (sin líneas vacías al final)."""
    out = []
    for ln in lines:
        if H._plain(ln).lstrip().startswith(_BOX_TOPS):
            break
        out.append(ln)
    while out and not H._plain(out[-1]).strip():
        out.pop()
    return out


# Elección «regresar» del menú de sesiones (Esc): el panel la imprime y el
# motor reabre el hub (o sale al shell si no se vino del hub).
BACK = "BACK"


def session_screen(items, selected, width, height, context, banner='',
                   notice='', title=None, hints=None):
    # Keep a full illustration only when both dimensions allow the picker.
    illustrated = title_only(banner.splitlines())
    bw = max(map(H.vis,illustrated),default=0)
    box_w = box_left = None
    if illustrated and bw < width and len(illustrated) <= height-12:
        box_left = max(0, (width - 1 - bw) // 2)     # banner CENTRADO
        pad = ' ' * box_left
        top = [pad + ln if ln.strip() else ln for ln in illustrated] + ['']
        box_w = bw        # la caja SESIONES hereda ancho+margen del banner:
                          # los dos marcos quedan ALINEADOS (bloque único)
    else:
        top = heading(context['name'],'',width)       # solo el título
    spare = max(1,height-1-len(top)-4)
    rows = picker_frame(items,selected,width,spare+20,box_w=box_w,left=box_left,
                        notice=notice,title=title,hints=hints)
    return [H.clip(x,width-1) for x in (top+rows)[:height-1]]

def _apply_theme_osc(palette):
    """Fondo/tinta del TEMA activo — paridad EXACTA con el hub (front.py):
    un tema trae su propio fondo (tui.osc en themes/<id>/theme.json); sin
    OSC (terminal sin color) se RESTAURAN los colores de la terminal. Sin el
    else, al volver de un tema oscuro el fondo viejo se quedaba pegado en el
    picker (gap del cambio de tema en vivo)."""
    import theme
    if getattr(palette, 'OSC', None):
        theme.apply_colors(palette.OSC)
    else:
        theme.reset()


def live_picker(items, script, keys='', notice='', selected=0, title=None, hints=None):
    """TTY picker with idle theme/size refresh and an unchanged selected row.
    Devuelve el índice elegido, BACK (Esc/Ctrl+C) o None sin terminal.
    Sesiones v2 (opcional; sin estos argumentos es el de siempre): una tecla
    de `keys` (p. ej. 'au') devuelve (tecla, índice marcado); `notice`,
    `title` y `hints` van a la caja (picker_frame); `selected` = la fila
    marcada al entrar."""
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
    selected = max(0, min(int(selected or 0), len(items) - 1))
    signature, banner = None, ''
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
                UI.paint(out,session_screen(items,selected,size.columns,size.lines,context,banner,
                                            notice=notice,title=title,hints=hints),first=signature is None)
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
            if key == '\x1b':               # Esc suelto: de vuelta al hub
                return BACK
            if key == '\x03':                # Ctrl+C: salir, NO «+ Sesión nueva»
                return BACK
            if key == 'up':
                selected = (selected-1)%len(items)
            elif key == 'down':
                selected = (selected+1)%len(items)
            elif key in '123456789' and key and int(key) <= len(items):
                return int(key)-1
            elif keys and len(key) == 1 and key.lower() in keys:
                return (key.lower(), selected)
            else:
                continue
            redraw = True
    finally:
        if old is not None:
            termios.tcsetattr(inp.fileno(),termios.TCSADRAIN,old)
        if sys.platform != 'win32':
            inp.close()
        out.close()


# ── sesiones v2: el menú de pestañas con ARCHIVAR (todos los dashboards) ─────
#: kinds de las filas que agrega este menú (los dashboards no las conocen)
ARCHIVADAS = 'ARCH'
VOLVER = 'LIST'


def _hints_lista():
    # a/u antes de 1-9: si no caben, keyline cede primero los del medio
    # desde el final (1-9), y conserva ↑↓ y Esc
    return (('↑↓', _t('greeter.hint.choose', 'elige')),
            ('Enter', _t('greeter.hint.open', 'abre')),
            ('a', _t('sesiones.hint.archive', 'archiva')),
            ('u', _t('sesiones.hint.undo', 'deshace')),
            ('1-9', _t('greeter.hint.direct', 'directo')),
            ('Esc', _t('greeter.hint.back', 'regresa')))


def _hints_archivadas():
    return (('↑↓', _t('greeter.hint.choose', 'elige')),
            ('Enter', _t('sesiones.hint.restore', 'recupera y abre')),
            ('u', _t('sesiones.hint.undo', 'deshace')),
            ('Esc', _t('sesiones.hint.back', 'vuelve')))


def _t_kw(key, es, **kw):
    s = _t(key, es)
    try:
        return s.format(**kw)
    except Exception:
        return es.format(**kw)


def filas_archivadas(brain, agent):
    """[(nombre, «archivada <fecha>», ("WS", id, nombre))] de las pestañas
    archivadas, la más reciente primero, y al final «← Volver»."""
    import sessions_registry as reg
    out = []
    for t in reg.archivadas(brain, agent):
        wid = reg.resume_id(brain, agent, t['name'], 'claude-code') or None
        out.append((t['name'],
                    _t_kw('sesiones.menu.sub', 'archivada {fecha}', fecha=t.get('archivada') or '—'),
                    ('WS', wid, t['name'])))
    out.append((_t('sesiones.menu.volver', '← Volver'),
                _t('sesiones.menu.volver_sub', 'a tus pestañas'), (VOLVER, None, None)))
    return out


def _aviso_recuperadas(nombres):
    if not nombres:
        return _t('sesiones.menu.nada', 'Nada que deshacer')
    if len(nombres) == 1:
        return _t_kw('sesiones.menu.recuperada', 'Recuperé «{name}»', name=nombres[0])
    return _t_kw('sesiones.menu.recuperadas', 'Recuperé {n} pestañas', n=len(nombres))


def menu_sesiones(brain, agent, menu_items, script, fallback=None, picker=None):
    """El menú de pestañas de un agente con ARCHIVAR (sesiones v2): UNA sola
    implementación para todos los dashboards (repo, plantilla y los que
    viven en un cerebro y la llamen).

      · `a` archiva la pestaña marcada: sale del menú en todas tus máquinas,
        nada se borra (sessions_registry.archivar); queda una línea
        «Archivada «x» · u para deshacer»;
      · `u` deshace el último archivo, también el automático;
      · la fila «Archivadas (N)», al final, lista las archivadas: Enter la
        recupera y la abre, Esc vuelve.

    `menu_items()` = las filas del dashboard [(etiqueta, estado, kind)]; se
    vuelve a pedir tras cada cambio. `fallback(items)` = el picker propio del
    dashboard sin terminal (índice o BACK): ahí no hay teclas de archivar.
    `picker` = live_picker (las pruebas lo sustituyen). Devuelve el kind
    elegido (("WS", id, nombre) / ("NEW", None, None)) o BACK."""
    import sessions_registry as reg
    picker = picker or live_picker
    sel, vista = 0, 'lista'
    try:                       # «archivé N pestañas…» del archivo automático
        aviso = reg.aviso_pendiente(brain, menu=True)
    except Exception:
        aviso = ''
    while True:
        if vista == 'lista':
            items = list(menu_items())
            try:
                n = len(reg.archivadas(brain, agent))
            except Exception:
                n = 0
            if n:
                items.append((_t_kw('sesiones.menu.fila', 'Archivadas ({n})', n=n),
                              _t('sesiones.menu.fila_sub', 'las que quitaste del menú'),
                              (ARCHIVADAS, None, None)))
            r = picker(items, script, keys='au', notice=aviso, selected=sel,
                       hints=_hints_lista())
        else:
            items = filas_archivadas(brain, agent)
            r = picker(items, script, keys='u', notice=aviso, selected=sel,
                       title=_t('sesiones.menu.titulo', 'ARCHIVADAS'), hints=_hints_archivadas())
        aviso = ''
        if r is None:                    # sin terminal: el picker de siempre
            base = [it for it in items if it[2][0] not in (ARCHIVADAS, VOLVER)] \
                if vista == 'lista' else list(menu_items())
            if fallback is None or not base:
                return BACK
            k = fallback(base)
            return BACK if k == BACK else base[k][2]
        if r == BACK:
            if vista == 'lista':
                return BACK
            vista, sel = 'lista', 0
            continue
        if isinstance(r, tuple):
            tecla, i = r
            sel = i
            kind = items[i][2] if 0 <= i < len(items) else (None,)
            if tecla == 'a' and vista == 'lista' and kind[0] == 'WS':
                aviso = (_t_kw('sesiones.menu.archivada', 'Archivada «{name}» · u para deshacer',
                               name=kind[2])
                         if reg.archivar(brain, agent, kind[2]) else
                         _t_kw('sesiones.menu.no_pude', 'No pude archivar «{name}»', name=kind[2]))
            elif tecla == 'u':
                aviso = _aviso_recuperadas(reg.desarchivar_ultimas(brain, agent))
            continue
        kind = items[r][2]
        if kind[0] == ARCHIVADAS:
            vista, sel = 'archivadas', 0
            continue
        if kind[0] == VOLVER:
            vista, sel = 'lista', 0
            continue
        if vista == 'archivadas' and kind[0] == 'WS':
            reg.desarchivar(brain, agent, kind[2])     # Enter = recupera y abre
        return kind
