"""WORKSPACE · usuarios_tui — sección USUARIOS: quién usa cada agente.

Mismo lenguaje que Motores (una caja centrada, section_box): a la izquierda
los usuarios del agente (más «+ usuario nuevo»), a la derecha lo que se puede
hacer con el elegido:
  soy yo en esta PC   · cambiar nombre   · unir a otro usuario…
Tab cambia de agente. Cada usuario tiene una «cédula» (un ID fijo en su
perfil, usuarios.py): el nombre de la carpeta es solo una etiqueta, así que
renombrar o unir nunca confunde a otra máquina. Nada se escribe a mano y
nada se borra. Qué es cada cosa: en `i`.
"""
import os
import sys
import time

import hublayout as HL
import section_box as SB
import section_frame as SF
import usuarios as U
from theme import screen as _theme_screen  # fondo/tinta del tema

_t = SF.t
LIST_W = 26
DETAIL_W = 44


def word():
    return HL.section_word('usuarios')


# ── datos ────────────────────────────────────────────────────────────────────
def _agents():
    """[(nombre, display, cerebro)] de los agentes con cerebro en esta PC."""
    out = []
    try:
        import agent_state
        for a in agent_state.snapshot().registered():
            b = a.get('brain') or ''
            if b and os.path.isdir(b):
                out.append((a.get('name', ''), a.get('display') or a.get('name', ''), b))
    except Exception:
        pass
    return out


def initial():
    S = {'agents': _agents(), 'agent': 0, 'user': 0, 'focus': 'list', 'opt': 0, 'msg': '',
         'edit': None, 'pick': None, 'confirm': None, 'rows': []}
    reload(S, asegurar=True)
    return S


def brain(S):
    return S['agents'][S['agent'] % len(S['agents'])][2] if S['agents'] else ''


def agent_name(S):
    return S['agents'][S['agent'] % len(S['agents'])][1] if S['agents'] else ''


def reload(S, asegurar=False):
    b = brain(S)
    if not b:
        S['rows'] = []
        return
    if asegurar:
        try:
            U.asegurar(b)            # lo automático: cédulas y marcas al día
        except Exception:
            pass
    try:
        S['rows'] = U.resumen(b)
    except Exception as e:
        S['rows'] = []
        S['msg'] = '✗ %s' % e
    S['user'] = max(0, min(S.get('user', 0), len(S['rows'])))
    S['firma'] = _firma(b)


def _firma(b):
    """Lo que cambia cuando llega algo de otra máquina por la sincronización
    (perfiles y carpetas de sesiones) o cambia el «soy yo» de esta PC."""
    out = []
    for d in (os.path.join(b, 'STATE', 'users'), os.path.join(b, 'STATE', 'sessions')):
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        st = e.stat()
                    except OSError:
                        continue
                    out.append((d, e.name, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((d, '', 0, 0))
    try:
        st = os.stat(os.path.join(b, '.claude', 'socio.local'))
        out.append(('socio.local', '', st.st_mtime_ns, st.st_size))
    except OSError:
        pass
    return tuple(sorted(out))


def _al_dia(S, ahora=None):
    """La sección se actualiza sola si el cerebro cambió en disco: otra
    máquina renombró, unió o creó un usuario y llegó por Obsidian. Se mira a
    lo más una vez por segundo y nunca a media edición. → True si recargó."""
    ahora = time.monotonic() if ahora is None else ahora
    if S.get('edit') or S.get('pick') or S.get('confirm') or ahora - S.get('visto', 0) < 1:
        return False
    S['visto'] = ahora
    b = brain(S)
    if not b or _firma(b) == S.get('firma'):
        return False
    antes = selected(S)
    reload(S)
    if antes:
        S['user'] = next((k for k, r in enumerate(S['rows'])
                          if (antes['id'] and r['id'] == antes['id']) or r['nombre'] == antes['nombre']),
                         S['user'])
    return True


def selected(S):
    """La fila elegida (dict) o None = «+ usuario nuevo»."""
    i = S.get('user', 0)
    return S['rows'][i] if i < len(S['rows']) else None


def options(S, row):
    """[(clave, etiqueta, valor)] del usuario elegido: bool = interruptor,
    texto = dato (solo se lee), '' = acción (›)."""
    if row is None:
        return [('new', _t('usuarios.o.new', 'crear usuario', 'create user'), '')]
    out = [('yo', _t('usuarios.o.me', 'soy yo en esta PC', "that's me on this PC"), bool(row['yo'])),
           ('rename', _t('usuarios.o.rename', 'cambiar nombre', 'rename'), '')]
    if len(S['rows']) > 1:
        out.append(('merge', _t('usuarios.o.merge2', 'unir a otro usuario…',
                                'merge into another user…'), ''))
    out += [('tabs', _t('usuarios.f.tabs', 'pestañas', 'tabs'), str(row['pestanas'])),
            ('alias', _t('usuarios.f.alias', 'antes se llamó', 'formerly'),
             ', '.join(row['alias']) or '—'),
            ('id', _t('usuarios.f.id', 'cédula', 'ID'), row['id'] or '—')]
    return out


_ACCIONES = ('new', 'rename', 'merge')
_DATOS = ('tabs', 'alias', 'id')


# ── pintar ───────────────────────────────────────────────────────────────────
def _chips(S):
    if S.get('edit'):
        return (('Enter', _t('usuarios.k.save', 'guarda', 'save')),
                ('Esc', _t('usuarios.k.cancel', 'cancela', 'cancel')))
    if S.get('confirm'):
        return (('Enter', _t('usuarios.k.merge', 'une', 'merge')),
                ('Esc', _t('usuarios.k.cancel', 'cancela', 'cancel')))
    if S.get('pick'):
        return (('↑↓', _t('usuarios.k.pick', 'elige', 'pick')),
                ('Enter', _t('usuarios.k.next', 'sigue', 'next')),
                ('Esc', _t('usuarios.k.cancel', 'cancela', 'cancel')))
    base = []
    if len(S['agents']) > 1:
        base.append(('Tab', _t('usuarios.k.agent', 'otro agente', 'other agent')))
    if S.get('focus') == 'detail':
        return tuple(base) + (('↑↓', _t('usuarios.k.option', 'opción', 'option')),
                              ('Enter', _t('usuarios.k.do', 'aplica', 'apply')),
                              ('←', _t('usuarios.k.to_list', 'a la lista', 'to the list')),
                              ('i', _t('usuarios.k.info', 'cómo funciona', 'how it works')))
    return tuple(base) + (('↑↓', _t('usuarios.k.pick', 'elige', 'pick')),
                          ('→', _t('usuarios.k.to_opts', 'sus opciones', 'its options')),
                          ('i', _t('usuarios.k.info', 'cómo funciona', 'how it works')),
                          ('q', _t('usuarios.k.back', 'vuelve', 'back')))


def _mark(S, row):
    """(palabra de estado, clave de color) para la lista."""
    if row['yo']:
        return (_t('usuarios.m.you', 'tú', 'you'), 'OK')
    if row['parecido']:
        return (_t('usuarios.m.same', '¿= {n}?', '= {n}?', n=row['parecido']), 'C')
    return (_t('usuarios.m.tabs', '{n} pest.', '{n} tabs', n=row['pestanas']), 'DIM')


def _detalle(S, K, iw):
    row = selected(S)
    if S.get('edit'):
        ed = S['edit']
        titulo = (_t('usuarios.e.new', 'Nombre del usuario nuevo', 'New user name') if ed['kind'] == 'new'
                  else _t('usuarios.e.rename', 'Nombre nuevo para «{n}»', 'New name for «{n}»', n=row['nombre']))
        limpio = U.limpiar_nombre(ed['text'])
        out = [HL.clip('%s%s%s' % (K['C'] + K['BO'], titulo, K['R']), iw), '',
               HL.clip('%s› %s%s▌%s' % (K['WH'], ed['text'], K['C'], K['R']), iw), '']
        if ed['text'] and limpio != ed['text']:
            out.append(HL.clip('%s%s%s' % (K['DIM'], _t('usuarios.e.as', 'se guardará como «{n}»',
                                                         'will be saved as «{n}»', n=limpio or '—'), K['R']), iw))
        out += ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in SB._wrap(_t(
            'usuarios.e.hint', 'letras, números y guiones; la cédula no cambia',
            'letters, numbers and dashes; the ID never changes'), iw)]
        return out, 2
    if S.get('confirm'):
        o, d = S['confirm']
        out = [HL.clip('%s%s%s' % (K['C'] + K['BO'], _t('usuarios.c.title', '¿Unir «{o}» con «{d}»?',
                                                        'Merge «{o}» into «{d}»?', o=o, d=d), K['R']), iw), '']
        out += ['%s%s%s' % (K['WH'], ln, K['R']) for ln in SB._wrap(_t(
            'usuarios.c.body', 'Las pestañas de «{o}» pasan a «{d}». Si una está en los dos, se queda la más '
            'nueva y la otra se guarda entera en history/. «{o}» queda como nombre anterior de «{d}»: '
            'otra máquina que diga «{o}» entra solita a «{d}». Nada se borra.',
            "«{o}»'s tabs move to «{d}». If a tab is in both, the newest stays and the other is kept whole "
            "in history/. «{o}» becomes a former name of «{d}»: another machine that says «{o}» lands in "
            "«{d}» on its own. Nothing is deleted.", o=o, d=d), iw)]
        return out, 0
    if S.get('pick'):
        cands = S['pick']['cands']
        out = [HL.clip('%s%s%s' % (K['C'] + K['BO'], _t('usuarios.p.title2', '«{n}» es la misma persona que… (se une a ese)',
                                                        '«{n}» is the same person as… (merges into it)', n=row['nombre']),
                                   K['R']), iw), '']
        fila = 0
        for k, c in enumerate(cands):
            on = k == S['pick']['sel']
            if on:
                fila = len(out)
            cur = ('%s%s %s' % (K['C'] + K['BO'], K['PTR'], K['R'])) if on else '  '
            out.append(HL.clip('%s%s%s%s' % (cur, (K['WH'] + K['BO']) if on else K['GREY'], c, K['R']), iw))
        return out, fila
    activo = S.get('focus') == 'detail'
    ops = options(S, row)
    S['opt'] = max(0, min(S.get('opt', 0), len(ops) - 1))
    lab_w = max(HL.vis(o[1]) for o in ops) + 2
    out, fila = [], 0
    for n, (key, lab, val) in enumerate(ops):
        on = activo and n == S['opt']
        if on:
            fila = len(out)
        cur = ('%s%s %s' % (K['C'] + K['BO'], K['PTR'], K['R'])) if on else '  '
        tinta = (K['WH'] + K['BO']) if on else K['GREY']
        if key in _ACCIONES:
            flecha = '%s›%s' % ((K['C'] + K['BO']) if on else K['DK'], K['R'])
            out.append(HL.clip('%s%s%s%s%s%s' % (cur, tinta, lab, K['R'],
                                                 ' ' * max(1, iw - 3 - HL.vis(lab)), flecha), iw))
            continue
        if isinstance(val, bool):
            valor = '%s %s%s%s' % (SB.switch(K, val), K['OK'] if val else K['DIM'],
                                    _t('usuarios.v.yes', 'sí', 'yes') if val else _t('usuarios.v.no', 'no', 'no'),
                                    K['R'])
        else:
            valor = '%s%s%s' % (K['DIM'], val, K['R'])
        out.append(HL.clip('%s%s%s%s%s' % (cur, tinta, HL.pad(lab, lab_w), K['R'], valor), iw))
    if row is None and not activo:
        out += [''] + ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in SB._wrap(_t(
            'usuarios.new.hint', 'Para otra persona que use este agente en su máquina.',
            'For another person who uses this agent on their machine.'), iw)]
    return out, fila


def _cuerpo(S, K, iw):
    items = [(r['nombre'],) + _mark(S, r) for r in S['rows']]
    items.append(('+ ' + _t('usuarios.l.new', 'usuario nuevo', 'new user'), '', '', 'C'))
    sel = S['user'] % len(items)
    der = S.get('focus') == 'detail' or any(S.get(k) for k in ('edit', 'pick', 'confirm'))
    tail = '◂' if der else '▸'
    cab = [HL.clip('%s%s%s %s%s%s' % (K['DIM'], _t('usuarios.agent', 'agente', 'agent'), K['R'],
                                      K['WH'] + K['BO'], agent_name(S), K['R']), iw), '']
    if iw < LIST_W + SB.SPLIT_GAP + 36:
        arriba = SB.pick_list(K, items, sel, iw, min(len(items), 8), sel_tail=tail)
        opciones, fila = _detalle(S, K, iw)
        S['_cur'] = len(cab) + len(arriba) + 2 + fila if der else len(cab) + min(sel, len(arriba) - 1)
        etiqueta = '%s · %s' % ((selected(S) or {}).get('nombre') or _t('usuarios.l.new', 'usuario nuevo',
                                                                          'new user'),
                                _t('usuarios.opts', 'opciones', 'options'))
        return cab + SB.stack(K, arriba, opciones, iw, label=etiqueta, active=der)
    opciones, fila = _detalle(S, K, iw - LIST_W - SB.SPLIT_GAP)
    izq = SB.pick_list(K, items, sel, LIST_W, max(len(opciones), min(len(items), 8)), sel_tail=tail)
    S['_cur'] = len(cab) + (fila if der else min(sel, len(izq) - 1))
    return cab + SB.split(K, izq, opciones, iw, LIST_W)


def info_blocks(S, K):
    return [
        ('h', _t('usuarios.info.h1', 'Usuarios con cédula', 'Users with an ID')),
        ('flow', [(_t('usuarios.info.n1', 'la cédula', 'the ID'), _t('usuarios.info.c1', 'nunca cambia', 'never changes')),
                  (_t('usuarios.info.n2', 'el nombre', 'the name'), _t('usuarios.info.c2', 'una etiqueta', 'just a label')),
                  (_t('usuarios.info.n3', 'esta PC', 'this PC'), _t('usuarios.info.c3', 'elige quién eres', 'picks who you are'))]),
        ('gap',),
        ('p', _t('usuarios.info.p1',
                 'Cada persona que usa un agente tiene un perfil en su cerebro (STATE/users/) con una cédula: '
                 'un ID fijo. Sus pestañas y su memoria viven en STATE/sessions/<nombre>/ y llevan la misma marca. '
                 'Como el cerebro viaja a tus otras máquinas, la lista de usuarios es la misma en todas.',
                 'Everyone who uses an agent has a profile in its brain (STATE/users/) with a fixed ID. Their '
                 'tabs and memory live in STATE/sessions/<name>/ with the same mark. The brain travels to your '
                 'other machines, so the user list is the same on all of them.')),
        ('h', _t('usuarios.info.h_opts', 'lo que puedes hacer', 'what you can do')),
        ('kv', [(_t('usuarios.o.me', 'soy yo en esta PC', "that's me on this PC"),
                 _t('usuarios.info.o_me', 'esta máquina te reconoce como ese usuario (solo esta máquina)',
                    'this machine recognizes you as that user (this machine only)')),
                (_t('usuarios.o.rename', 'cambiar nombre', 'rename'),
                 _t('usuarios.info.o_rename', 'cambia el nombre y la carpeta; el anterior queda como alias, '
                    'así otra máquina con el nombre viejo entra sola al nuevo',
                    'changes the name and the folder; the old one stays as an alias, so another machine '
                    'with the old name lands on the new one')),
                (_t('usuarios.o.merge2', 'unir a otro usuario…', 'merge into another user…'),
                 _t('usuarios.info.o_merge', 'une dos usuarios que son la misma persona (p. ej. el de la Mac y '
                    'el de Windows); se queda lo más nuevo de cada pestaña y nada se borra',
                    'merges two users who are the same person (e.g. the Mac one and the Windows one); the '
                    'newest of each tab stays and nothing is deleted')),
                (_t('usuarios.o.new', 'crear usuario', 'create user'),
                 _t('usuarios.info.o_new', 'para otra persona que use este agente',
                    'for another person who uses this agent'))]),
        ('gap',),
        ('dim', _t('usuarios.info.auto',
                   'Solo, al abrir un agente: los perfiles y pestañas sin cédula reciben una, y si esta máquina '
                   'usa un nombre viejo se corrige. No hace falta tocar ningún archivo.',
                   'On its own, when you open an agent: profiles and tabs without an ID get one, and if this '
                   'machine uses an old name it is fixed. No need to touch any file.')),
    ]


def render(S, w, h):
    K = SF.K()
    titulo = _t('usuarios.box', 'USUARIOS', 'USERS')
    if S.get('info'):
        return SB.info_frame(K, w, h, word(), _t('usuarios.info.title', 'CÓMO FUNCIONAN LOS USUARIOS',
                                                  'HOW USERS WORK'), info_blocks(S, K), state=S['info'], box_w=64)
    if not S['agents']:
        return SB.frame(K, w, h, word(), titulo, [_t('usuarios.none', 'Todavía no tienes agentes.',
                                                     "You don't have agents yet.")], _chips(S),
                        msg=S.get('msg', ''), box_w=44)
    return SB.frame(K, w, h, word(), titulo, lambda iw: _cuerpo(S, K, iw), _chips(S),
                    msg=S.get('msg', ''), cursor_line=lambda: S.get('_cur', 0),
                    box_w=LIST_W + SB.SPLIT_GAP + DETAIL_W,
                    stable_rows=max(min(len(S['rows']) + 3, 10), 8))


# ── acciones ─────────────────────────────────────────────────────────────────
def _guardar_edicion(S):
    ed = S['edit']
    b = brain(S)
    try:
        if ed['kind'] == 'new':
            c = U.crear(b, ed['text'])
            S['msg'] = '✓ ' + _t('usuarios.m.created', 'usuario «{n}» creado', 'user «{n}» created', n=c['nombre'])
            nombre = c['nombre']
        else:
            row = selected(S)
            c = U.renombrar(b, row['id'] or row['nombre'], ed['text'], revision=row['revision'])
            S['msg'] = '✓ ' + _t('usuarios.m.renamed', '«{o}» ahora se llama «{n}» (la cédula es la misma)',
                                 '«{o}» is now «{n}» (same ID)', o=row['nombre'], n=c['nombre'])
            nombre = c['nombre']
        S['edit'] = None
        reload(S)
        S['user'] = next((k for k, r in enumerate(S['rows']) if r['nombre'] == nombre), 0)
    except ValueError as e:
        S['msg'] = '✗ %s' % e


def _unir(S):
    o, d = S['confirm']
    S['confirm'] = None
    S['pick'] = None
    try:
        r = U.unir(brain(S), o, d)
        S['msg'] = '✓ ' + _t('usuarios.m.merged', '«{o}» unido a «{d}»: {n} pestaña(s); nada se borró',
                             '«{o}» merged into «{d}»: {n} tab(s); nothing was deleted',
                             o=o, d=d, n=len(r['movidas']) + len(r['dobles']))
        reload(S)
        S['user'] = next((k for k, r2 in enumerate(S['rows']) if r2['nombre'] == d), 0)
        S['focus'] = 'list'
    except ValueError as e:
        S['msg'] = '✗ %s' % e


def _aplica(S):
    row = selected(S)
    key = options(S, row)[S.get('opt', 0)][0]
    if key == 'new':
        S['edit'] = {'kind': 'new', 'text': ''}
    elif key == 'rename':
        S['edit'] = {'kind': 'rename', 'text': row['nombre']}
    elif key == 'merge':
        cands = [r['nombre'] for r in S['rows'] if r['nombre'] != row['nombre']]
        pre = cands.index(row['parecido']) if row.get('parecido') in cands else 0
        S['pick'] = {'cands': cands, 'sel': pre}
    elif key == 'yo':
        if row['yo']:
            S['msg'] = _t('usuarios.m.already', 'ya eres «{n}» en esta PC', "you're already «{n}» on this PC",
                          n=row['nombre'])
        else:
            try:
                U.elegir(brain(S), row['nombre'])
                S['msg'] = '✓ ' + _t('usuarios.m.me', 'en esta PC eres «{n}»', "on this PC you're «{n}»",
                                     n=row['nombre'])
                reload(S)
            except ValueError as e:
                S['msg'] = '✗ %s' % e
    elif key in _DATOS:
        S['msg'] = _t('usuarios.m.readonly', 'solo informativo', 'for information only')
    return True


def _edit_key(S, key):
    ed = S['edit']
    if key in ('\x1b',):
        S['edit'] = None
        S['msg'] = _t('usuarios.m.cancel', 'cancelado · nada cambió', 'cancelled · nothing changed')
    elif key in ('\r', '\n'):
        _guardar_edicion(S)
    elif key in ('\x08', '\x7f'):
        ed['text'] = ed['text'][:-1]
    elif len(key) == 1 and key.isprintable() and len(ed['text']) < 40:
        ed['text'] += key
    return True


def act(S, key):
    """True = sigue · False = sale (volver al hub)."""
    if key == '\x03':
        return False
    if S.get('edit'):
        return _edit_key(S, key)
    if S.get('confirm'):
        if key in ('\r', '\n'):
            _unir(S)
        else:
            S['confirm'] = None
            S['msg'] = _t('usuarios.m.cancel', 'cancelado · nada cambió', 'cancelled · nothing changed')
        return True
    if S.get('pick'):
        p = S['pick']
        if key in ('up', 'down'):
            p['sel'] = (p['sel'] + (-1 if key == 'up' else 1)) % max(1, len(p['cands']))
        elif key in ('\r', '\n') and p['cands']:
            S['confirm'] = (selected(S)['nombre'], p['cands'][p['sel']])
        elif key in ('\x1b', 'left', 'q'):
            S['pick'] = None
        return True
    if SB.info_key(S, key):
        return True
    if not S['agents']:
        return key not in ('q', 'Q', '\x1b')
    S['msg'] = ''
    if key == 'tab' and len(S['agents']) > 1:
        S['agent'] = (S['agent'] + 1) % len(S['agents'])
        S['user'], S['focus'], S['opt'] = 0, 'list', 0
        reload(S, asegurar=True)
        return True
    if S.get('focus') == 'detail':
        ops = options(S, selected(S))
        if key in ('\x1b', 'left', 'q', 'Q'):
            S['focus'] = 'list'
        elif key in ('up', 'down'):
            S['opt'] = (S.get('opt', 0) + (-1 if key == 'up' else 1)) % len(ops)
        elif key in ('\r', '\n', ' '):
            return _aplica(S)
        return True
    if key in ('q', 'Q', '\x1b'):
        return False
    n = len(S['rows']) + 1
    if key in ('up', 'down'):
        S['user'] = (S['user'] + (-1 if key == 'up' else 1)) % n
        S['opt'] = 0
    elif key in ('\r', '\n', 'right', ' '):
        if selected(S) is None:
            S['edit'] = {'kind': 'new', 'text': ''}
        else:
            S['focus'], S['opt'] = 'detail', 0
    return True


# ── loop (mismo que Motores) ─────────────────────────────────────────────────
@_theme_screen
def run():
    S = initial()
    try:
        import _console
        live = _console.interactive()
    except Exception:
        live = sys.stdin.isatty()
    if not live:
        print('\n'.join(render(S, 110, 44)))
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
                _al_dia(S)
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
                _al_dia(S)
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
