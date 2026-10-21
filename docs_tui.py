"""WORKSPACE · docs_tui — sección DOCUMENTACIÓN: todo lo que hace Workspace.

Mismo lenguaje que Usuarios (una caja centrada, section_box): a la izquierda
el mapa completo de la memoria y los 13 capítulos, en el orden en que los
vives; a la derecha el elegido. El primer renglón (o la tecla m) abre el mapa
completo en pantalla grande (docs_mapa); la fila «Mapa de la memoria» de la
portada del hub lo abre directo (run_mapa). Cada capítulo trae:

  · un mapa (cajas en fila, brain_view.pipeline) y 3–4 frases cortas;
  · EN ESTA PC   una línea real del agente elegido (solo lectura);
  · COMPRUÉBALO  el archivo, la carpeta o el comando que lo demuestra
                 (Enter o → lo abre; un comando queda listo para copiar);
  · SE APAGA EN  el ajuste que lo cambia, o por qué no se apaga.

Tab cambia de agente (el dato en vivo es de ese agente). El contenido vive
en docs_hub.py (español e inglés); aquí solo se pinta. Esta pantalla jamás
escribe nada: lee y, si se lo pides, abre con el programa del sistema.
"""
import os
import subprocess
import sys
import time

import docs_hub as D
import hublayout as HL
import section_box as SB
import section_frame as SF
from theme import screen as _theme_screen  # fondo/tinta del tema

_t = SF.t
LIST_W = 31
DETAIL_W = 60
#: Filas de la pantalla que no son contenido (wordmark, botones, bordes,
#: aire); con poco alto, wordmark compacto y botones de una línea.
_RESTO = 11
_RESTO_CHICO = 8
#: Con menos ancho que esto la derecha no cabe al lado: la lista va arriba.
_MIN_DER = 40


def word():
    return HL.section_word('documentacion')


# ── datos ────────────────────────────────────────────────────────────────────
def _agents():
    """[{name, display, brain, engine}] de los agentes con cerebro en esta PC."""
    out = []
    try:
        import agent_state
        for a in agent_state.snapshot().registered():
            b = a.get('brain') or ''
            if b and os.path.isdir(b):
                out.append({'name': a.get('name', ''), 'display': a.get('display') or a.get('name', ''),
                            'brain': b, 'engine': a.get('engine') or ''})
    except Exception:
        pass
    return out


def initial():
    """`cap` = -1: el renglón del mapa completo (el primero de la lista);
    `mapa` = el estado del mapa en pantalla grande, o None."""
    return {'agents': _agents(), 'agent': 0, 'cap': -1, 'msg': '', 'vivo': {}, 'mapa': None}


def ctx(S):
    return S['agents'][S['agent'] % len(S['agents'])] if S['agents'] else {}


def es_mapa(S):
    """¿Está elegido el renglón del mapa completo?"""
    return S.get('cap', 0) < 0


def cap(S):
    caps = D.capitulos()
    return caps[max(0, S['cap']) % len(caps)]


def vivo(S, c):
    """«En esta PC» del capítulo para el agente elegido, una vez por agente e
    idioma (no se relee en cada repintado)."""
    clave = (S['agent'], c['id'], D.lang())
    if clave not in S['vivo']:
        S['vivo'][clave] = D.en_esta_pc(c, ctx(S)) if S['agents'] else _t(
            'docs.no_agent_live', '— (aún no tienes agentes)', '— (no agents yet)')
    return S['vivo'][clave]


# ── pintar ───────────────────────────────────────────────────────────────────
def _chips(S):
    out = [('↑↓', _t('docs.k.chapter', 'capítulo', 'chapter'))]
    if len(S['agents']) > 1:
        out.append(('Tab', _t('docs.k.agent', 'otro agente', 'other agent')))
    out += [('Enter', _t('docs.k.open', 'abre', 'opens')),
            ('m', _t('docs.k.map', 'el mapa', 'the map')),
            ('i', _t('docs.k.info', 'cómo leer esto', 'how to read this')),
            ('q', _t('docs.k.back', 'vuelve', 'back'))]
    return tuple(out)


def _envolver(txt, w):
    """Envuelve por palabras; una palabra más larga que el ancho (una ruta)
    se parte después de una «/» en vez de cortarse con «…»."""
    w = max(8, w)
    out = []
    for ln in SB._wrap(txt, w):
        while HL.vis(ln) > w:
            corte = ln.rfind('/', 0, w) + 1 or w
            out.append(ln[:corte])
            ln = ln[corte:]
        out.append(ln)
    return out


def _mapa(K, tx, w):
    """El mapa del capítulo con brain_view.pipeline; si no cabe, la misma
    cadena en texto («a → b → c»). Nunca un mapa mutilado."""
    nodos, tramos, nota = tx['mapa']
    try:
        import agents_tui
        import brain_view
        lines = brain_view.pipeline(HL, K, agents_tui._mk, w, 5, nodos, tramos, nota)
    except Exception:
        lines = None
    if lines:
        return [ln.rstrip() for ln in lines]
    cadena = ' → '.join(str(n[0]).partition('|')[2] or str(n[0]) for n in nodos)
    out = ['%s%s%s' % (K['C'] + K['BO'], ln, K['R']) for ln in _envolver(cadena, w)]
    return out + ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in _envolver(nota, w)]


def _puntos(K, c, tx, w):
    """Las filas «cuándo → qué» (si el capítulo las trae) y las frases."""
    out = []
    fil = D.filas(c)
    if fil:
        kw = min(max(HL.vis(k) for k, _v, _c in fil) + 2, max(8, w // 2))
        for k, v, tono in fil:
            col = {'ok': K['OK'], 'c': K['C'], 'dk': K['DIM']}.get(tono, K['WH'])
            sub = _envolver(v, w - kw)
            out.append('%s%s%s%s%s%s' % (col + K['BO'], HL.pad(HL.clip(k, kw - 1), kw), K['R'],
                                          K['GREY'], sub[0], K['R']))
            out += [' ' * kw + '%s%s%s' % (K['GREY'], s, K['R']) for s in sub[1:]]
    if fil and tx.get('puntos'):
        out.append('')
    for p in tx.get('puntos') or ():
        for n, ln in enumerate(_envolver(p, w - 2)):
            out.append('%s%s%s %s%s%s' % (K['DK'], '·' if n == 0 else ' ', K['R'], K['GREY'], ln, K['R']))
    return out


def _filas(S, K, c, w):
    """Las tres filas: EN ESTA PC · COMPRUÉBALO · SE APAGA EN."""
    etiquetas = (_t('docs.row.live', 'EN ESTA PC', 'ON THIS PC'),
                 _t('docs.row.check', 'COMPRUÉBALO', 'CHECK IT'),
                 _t('docs.row.off', 'SE APAGA EN', 'TURN OFF IN'))
    lw = max(HL.vis(e) for e in etiquetas) + 2
    vw = max(8, w - lw)
    enter = _t('docs.row.enter', '(Enter)', '(Enter)')
    valores = ((K['OK'] + K['BO'], K['WH'], vivo(S, c), ''),
               (K['DIM'], K['C'], D.mostrar(c, ctx(S)), enter),
               (K['DIM'], K['GREY'], D.apaga(c), ''))
    out = []
    for etq, (ce, cv, val, cola) in zip(etiquetas, valores):
        sub = _envolver(val, vw)
        if cola:
            if HL.vis(sub[-1]) + 2 + HL.vis(cola) <= vw:
                sub[-1] = sub[-1] + '\0' + cola
            else:
                sub.append('\0' + cola)
        for n, ln in enumerate(sub):
            txt, _s, extra = ln.partition('\0')
            ln = '%s%s%s' % (cv, txt, K['R']) + (('  ' if txt else '') + '%s%s%s' % (K['DK'], extra, K['R'])
                                                 if extra else '')
            pre = '%s%s%s' % (ce, HL.pad(etq, lw), K['R']) if n == 0 else ' ' * lw
            out.append(HL.clip(pre + ln, w))
    return out


def _intro_mapa(K, w):
    """Lo que se ve a la derecha con el renglón del mapa elegido: un mapita,
    qué trae y la fila que dice cómo abrirlo."""
    tx = D.mapa_texto(D.MAPA_INTRO)
    puntos = []
    for p in tx['puntos']:
        for n, ln in enumerate(_envolver(p, w - 2)):
            puntos.append('%s%s%s %s%s%s' % (K['DK'], '·' if n == 0 else ' ', K['R'], K['GREY'], ln, K['R']))
    etq = _t('docs.row.map', 'ÁBRELO', 'OPEN IT')
    fila = HL.clip('%s%s%s  %s%s%s' % (K['OK'] + K['BO'], etq, K['R'], K['C'] + K['BO'], tx['abre'], K['R']), w)
    return tx, _mapa(K, tx, w), puntos, [fila]


def _detalle(S, K, w, alto, titulo=True):
    """El capítulo elegido en `alto` filas como mucho: si no cabe, cede el
    mapa y después recorta frases (y lo dice); las tres filas de abajo
    siempre quedan. `titulo`=False cuando la regla de arriba ya lo nombra."""
    if es_mapa(S):
        tx, mapa, puntos, filas = _intro_mapa(K, w)
        c = None
    else:
        c = cap(S)
        tx = D.texto(c)
        mapa = _mapa(K, tx, w)
        puntos = _puntos(K, c, tx, w)
        filas = _filas(S, K, c, w)
    cabeza = [HL.clip('%s%s%s' % (K['C'] + K['BO'], tx['titulo'].upper(), K['R']), w), ''] \
        if titulo else []
    libre = alto - len(cabeza) - len(filas) - 1
    if len(mapa) + 1 + len(puntos) <= libre:
        cuerpo = mapa + [''] + puntos
    elif len(puntos) <= libre:
        cuerpo = puntos
    elif libre > 0:
        mas = _t('docs.more', '… (agranda la ventana para leer todo)',
                 '… (enlarge the window to read it all)')
        cuerpo = puntos[:libre - 1] + [HL.clip('%s%s%s' % (K['DIM'], mas, K['R']), w)]
    else:
        cuerpo = []
    return cabeza + cuerpo + ([''] if cuerpo or cabeza else []) + filas


def _items(S):
    out = [(' ◆ %s' % D.mapa_texto(D.MAPA_INTRO)['corto'], '')]
    for n, c in enumerate(D.capitulos(), 1):
        out.append(('%2d %s' % (n, D.texto(c)['corto']), ''))
    return out


def _titulo(S):
    return D.mapa_texto(D.MAPA_INTRO)['titulo'] if es_mapa(S) else D.texto(cap(S))['titulo']


def _alto(h):
    """Filas que puede ocupar el cuerpo de la caja en una terminal de `h`.
    Con alto de sobra caben el wordmark y los botones grandes; con poco, la
    caja se queda con más filas (la cabecera y los botones se achican)."""
    return max(8, (h - 1) - (_RESTO if h >= 40 else _RESTO_CHICO))


def _cuerpo(S, K, iw, h):
    if S['agents']:
        cab = [HL.clip('%s%s%s %s%s%s' % (K['DIM'], _t('docs.agent', 'agente', 'agent'), K['R'],
                                          K['WH'] + K['BO'], ctx(S)['display'], K['R']), iw), '']
    else:
        cab = [HL.clip('%s%s%s' % (K['DIM'], _t('docs.no_agent', 'aún no tienes agentes: el dato '
                                                 'en vivo aparece al crear uno',
                                                 'no agents yet: live data shows up once you '
                                                 'create one'), K['R']), iw), '']
    items = _items(S)
    sel = (S['cap'] + 1) % len(items)
    alto = _alto(h) - len(cab)
    if iw < LIST_W + SB.SPLIT_GAP + _MIN_DER:
        # angosto: la lista arriba (una ventanita) y el capítulo abajo, con
        # su nombre en la regla
        filas_lista = 3 if alto < 24 else 5
        arriba = SB.pick_list(K, items, sel, iw, filas_lista, sel_tail='▸')
        det = _detalle(S, K, iw, alto - len(arriba) - 2, titulo=False)
        S['_cur'] = len(cab) + next((k for k, ln in enumerate(arriba) if '▸' in ln), 0)
        return cab + SB.stack(K, arriba, det, iw, label=_titulo(S), active=True)
    det = _detalle(S, K, iw - LIST_W - SB.SPLIT_GAP, alto)
    izq = SB.pick_list(K, items, sel, LIST_W, max(len(det), min(len(items), alto)), sel_tail='▸')
    S['_cur'] = len(cab) + next((k for k, ln in enumerate(izq) if '▸' in ln), 0)
    return cab + SB.split(K, izq, det, iw, LIST_W)


def info_blocks(S, K):
    return [
        ('h', _t('docs.info.h1', 'Cómo leer esta sección', 'How to read this section')),
        ('flow', [(_t('docs.info.n1', 'el mapa', 'the map'), _t('docs.info.c1', 'qué pasa, en orden', 'what happens, in order')),
                  (_t('docs.info.n2', 'en esta PC', 'on this PC'), _t('docs.info.c2', 'el dato real', 'the real data')),
                  (_t('docs.info.n3', 'compruébalo', 'check it'), _t('docs.info.c3', 'ábrelo tú', 'open it yourself'))]),
        ('gap',),
        ('p', _t('docs.info.p1',
                 'Cada capítulo cuenta una parte de lo que hace Workspace, en el orden en que lo vives: '
                 'abrir una pestaña, trabajar, cerrar, viajar a otra máquina… Sin letra chica.',
                 'Each chapter tells one part of what Workspace does, in the order you live it: opening '
                 'a tab, working, closing, moving to another machine… No fine print.')),
        ('h', _t('docs.info.h_rows', 'las tres filas de abajo', 'the three rows at the bottom')),
        ('kv', [(_t('docs.row.live', 'EN ESTA PC', 'ON THIS PC'),
                 _t('docs.info.live', 'lo que pasa ahora con el agente elegido (Tab cambia de agente); se lee '
                    'sin cambiar nada', 'what is happening now with the chosen agent (Tab switches agent); '
                    'it is read without changing anything')),
                (_t('docs.row.check', 'COMPRUÉBALO', 'CHECK IT'),
                 _t('docs.info.check', 'el archivo, la carpeta o el comando que lo demuestra. Enter (o →) lo '
                    'abre; un comando queda escrito abajo, listo para copiar en tu terminal',
                    'the file, folder or command that proves it. Enter (or →) opens it; a command is '
                    'written below, ready to copy into your terminal')),
                (_t('docs.row.off', 'SE APAGA EN', 'TURN OFF IN'),
                 _t('docs.info.off', 'el ajuste que lo cambia (capítulo 13), o por qué no se apaga',
                    'the setting that changes it (chapter 13), or why it cannot be turned off'))]),
        ('gap',),
        ('dim', _t('docs.info.truth',
                   'Si un archivo, comando o ajuste citado aquí deja de existir, una prueba automática de '
                   'Workspace falla: así esta sección no se queda contando algo que ya no es cierto.',
                   'If a file, command or setting quoted here stops existing, an automatic Workspace '
                   'test fails: that way this section never keeps telling something that is no longer '
                   'true.')),
    ]


def _estable(S, K, w, h):
    """El alto del capítulo MÁS alto en este tamaño: con él la caja no se
    mueve al cambiar de capítulo (solo crece o se encoge hacia abajo). Se
    mide una vez por tamaño, idioma y agente."""
    _pw, iw = SB.widths(w, LIST_W + SB.SPLIT_GAP + DETAIL_W)
    clave = (iw, h, D.lang(), S['agent'])
    if S.get('_est', (None, 0))[0] != clave:
        actual, cur = S['cap'], S.get('_cur', 0)
        alto = 0
        for i in range(-1, len(D.capitulos())):
            S['cap'] = i
            alto = max(alto, len(_cuerpo(S, K, iw, h)))
        S['cap'], S['_cur'] = actual, cur
        S['_est'] = (clave, alto)
    return S['_est'][1]


def render(S, w, h):
    K = SF.K()
    if S.get('mapa') is not None:
        import docs_mapa
        S['mapa']['ctx'] = ctx(S)
        # desde la portada del hub el mapa es su propia sección: MEMORIA
        palabra = HL.section_word('memoria') if S.get('solo_mapa') else word()
        return docs_mapa.render(S['mapa'], w, h, palabra)
    if S.get('info'):
        return SB.info_frame(K, w, h, word(), _t('docs.info.title', 'CÓMO LEER ESTA SECCIÓN',
                                                  'HOW TO READ THIS SECTION'),
                             info_blocks(S, K), state=S['info'], box_w=64)
    return SB.frame(K, w, h, word(), _t('docs.box', 'CÓMO FUNCIONA', 'HOW IT WORKS'),
                    lambda iw: _cuerpo(S, K, iw, h), _chips(S),
                    msg=S.get('msg', ''), cursor_line=lambda: S.get('_cur', 0),
                    box_w=LIST_W + SB.SPLIT_GAP + DETAIL_W, stable_rows=_estable(S, K, w, h))


# ── acciones ─────────────────────────────────────────────────────────────────
def abrir_con_el_sistema(path):
    """Abre un archivo o carpeta con el programa del sistema (como doble clic).
    → 'abierto', o 'carpeta' si no hay programa asociado y se mostró marcado en
    su carpeta. OSError si tampoco eso funcionó (regla 3: el «✓» lo da el
    código de salida, no haberlo lanzado)."""
    if os.name == 'nt':
        try:
            os.startfile(path)                     # noqa: S606 (es la intención)
            return 'abierto'
        except OSError:
            # sin programa asociado (p. ej. .jsonl): su carpeta, con él marcado
            subprocess.Popen(['explorer', '/select,', path])
            return 'carpeta'
    if sys.platform == 'darwin':
        # `open` vuelve enseguida (LaunchServices) y sale ≠ 0 si ninguna app
        # abre ese tipo (p. ej. .jsonl): entonces se muestra en Finder
        for cmd, modo in ((['open', path], 'abierto'), (['open', '-R', path], 'carpeta')):
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace', timeout=15)
            if r.returncode == 0:
                return modo
        raise OSError((r.stderr or '').strip() or 'open %d' % r.returncode)
    subprocess.Popen(['xdg-open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 'abierto'


def _abrir(S, c=None):
    """Abre lo que demuestra `c` (el capítulo elegido, o una parte del mapa):
    el archivo o la carpeta con el programa del sistema, o deja el comando
    listo para copiar. El resultado queda en S['msg']."""
    c = c or cap(S)
    kind = c['compruebalo'][0]
    if kind == 'comando':
        S['msg'] = _t('docs.m.copy', 'cópialo en tu terminal: {c}', 'copy it into your terminal: {c}',
                      c=D.comando(c, ctx(S), completo=True))
        return True
    path = D.ruta(c, ctx(S))
    if not path:
        S['msg'] = _t('docs.m.no_agent', 'esto vive en el cerebro de un agente: crea uno primero',
                      "this lives in an agent's brain: create one first")
        return True
    if not os.path.exists(path):
        S['msg'] = _t('docs.m.missing', 'todavía no existe en esta PC: {p}', 'not on this PC yet: {p}',
                      p=D.corto(path))
        return True
    try:
        if abrir_con_el_sistema(path) == 'carpeta':
            S['msg'] = '✓ ' + (_t('docs.m.revealed_mac', 'ninguna app lo abre: lo marqué en Finder: {p}',
                                  'no app opens it: highlighted in Finder: {p}', p=D.corto(path))
                               if sys.platform == 'darwin' else
                               _t('docs.m.revealed', 'ningún programa lo abre: lo marqué en su carpeta: {p}',
                                  'no program opens it: highlighted in its folder: {p}', p=D.corto(path)))
        else:
            S['msg'] = '✓ ' + _t('docs.m.opened', 'abierto: {p}', 'opened: {p}', p=D.corto(path))
    except Exception as e:
        S['msg'] = '✗ ' + _t('docs.m.fail', 'no pude abrirlo ({e}): {p}', "couldn't open it ({e}): {p}",
                             e=type(e).__name__, p=D.corto(path))
    return True


def _act_mapa(S, key):
    """Las teclas con el mapa completo abierto: las suyas (docs_mapa.act);
    q/Esc vuelve a los capítulos y Enter abre lo que demuestra la parte."""
    import docs_mapa
    M = S['mapa']
    if key == 'tab' and len(S['agents']) > 1:
        S['agent'] = (S['agent'] + 1) % len(S['agents'])
        return True
    r = docs_mapa.act(M, key)
    if r == 'abrir':
        _abrir(S, docs_mapa.actual(M))
        M['msg'], S['msg'] = S['msg'], ''
    elif r is False:
        if S.get('solo_mapa'):                     # abierto desde el hub: vuelve al hub
            return False
        S['mapa'] = None
    return True


def act(S, key):
    """True = sigue · False = sale (volver al hub)."""
    if key == '\x03':
        return False
    if S.get('mapa') is not None:
        return _act_mapa(S, key)
    if SB.info_key(S, key):
        return True
    S['msg'] = ''
    if key in ('q', 'Q', '\x1b'):
        return False
    n = len(D.capitulos()) + 1                    # el renglón del mapa + los capítulos
    if key == 'tab' and len(S['agents']) > 1:
        S['agent'] = (S['agent'] + 1) % len(S['agents'])
    elif key in ('up', 'down'):
        S['cap'] = (S['cap'] + 1 + (-1 if key == 'up' else 1)) % n - 1
    elif key in ('m', 'M'):
        import docs_mapa
        S['mapa'] = docs_mapa.initial()
    elif key in ('\r', '\n', 'right', ' '):
        if es_mapa(S):
            import docs_mapa
            S['mapa'] = docs_mapa.initial()
            return True
        return _abrir(S)
    return True


# ── loop (mismo que Usuarios y Motores) ──────────────────────────────────────
@_theme_screen
def run():
    S = initial()
    try:
        import _console
        live = _console.interactive()
    except Exception:
        live = sys.stdin.isatty()
    if not live:
        S['cap'] = 0                               # sin terminal: el capítulo 1
        print('\n'.join(render(S, 110, 44)))
        return
    import engines_tui
    _loop_con(S, engines_tui)


def initial_mapa(agente=None):
    """El estado de run_mapa: el mapa ya abierto, con `agente` (su nombre)
    elegido si tiene cerebro en esta PC; si no, el primero."""
    import docs_mapa
    S = initial()
    S['solo_mapa'] = True
    S['mapa'] = docs_mapa.initial()
    S['mapa']['al_hub'] = True
    nombres = [str(a.get('name', '')).lower() for a in S['agents']]
    if agente and str(agente).lower() in nombres:
        S['agent'] = nombres.index(str(agente).lower())
    return S


@_theme_screen
def run_mapa(agente=None):
    """El mapa de la memoria directo, sin los capítulos: la fila «Mapa de la
    memoria» de la portada del hub (pedido del dueño 2026-10-19: en
    Documentación quedaba escondido). Abre con el agente que estaba apuntado
    en el hub; q/Esc regresa al hub."""
    S = initial_mapa(agente)
    try:
        import _console
        live = _console.interactive()
    except Exception:
        live = sys.stdin.isatty()
    if not live:
        print('\n'.join(render(S, 150, 50)))
        return
    import engines_tui
    _loop_con(S, engines_tui)


def _loop_con(S, base):
    """El loop de teclado de Motores (Windows y Mac), con el render y las
    acciones de esta sección."""
    import responsive_ui
    if os.name == 'nt':
        import msvcrt
        out = sys.stdout
        out.write('\033[?1049h\033[?25l')
        try:
            first, last = True, None
            while True:
                w, h = base._size(out)
                frame = render(S, w, h)
                if frame != last:
                    responsive_ui.paint(out, frame, first=first)
                    first, last = False, frame
                if not msvcrt.kbhit():
                    time.sleep(.05)
                    continue
                key = msvcrt.getwch()
                if key in ('\x00', '\xe0'):
                    key = {'H': 'up', 'P': 'down', 'K': 'left', 'M': 'right'}.get(msvcrt.getwch(), '')
                if not act(S, 'tab' if key == '\t' else key):
                    return
        finally:
            out.write('\033[?25h\033[?1049l')
            out.flush()
    else:
        import termios
        import tty
        import select
        from add_agent_tui import _read_key_unix
        fd = os.open('/dev/tty', os.O_RDWR)
        out = open('/dev/tty', 'w', encoding='utf-8')
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            out.write('\033[?1049h\033[?25l')
            first, last = True, None
            while True:
                w, h = base._size(out)
                frame = render(S, w, h)
                if frame != last:
                    responsive_ui.paint(out, frame, first=first)
                    first, last = False, frame
                if select.select([fd], [], [], .15)[0] and not act(S, _read_key_unix(fd, select)):
                    return
        finally:
            out.write('\033[?25h\033[?1049l')
            out.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            out.close()
            os.close(fd)


if __name__ == '__main__':
    run()
