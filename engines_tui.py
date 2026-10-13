"""WORKSPACE · engines_tui — sección MOTORES: qué motores tienes y cómo dejarlos listos.

Rediseño 2026-10 (transparencia · simpleza · utilidad real). Un motor es un
programa oficial (Claude Code, Codex, Antigravity) que corre a tus agentes.
La pantalla dice, por motor, lo único que importa y la acción siguiente:

  instalado   el programa está en esta máquina (o no) — Enter lo instala
              con el instalador oficial (muestra comando y fuente, confirma)
  sesión      sin verificar / verificada / requiere login — v verifica,
              Enter abre el login del propio programa (Workspace no ve tu cuenta)
  atajo M     si la tecla M del hub lo ofrece — m lo pone o lo quita
  lo usan     qué agentes corren hoy con él (el motor de cada agente se
              cambia en Agentes)
  r recarga (si instalaste desde otra terminal) · q vuelve
"""
import os
import sys
import threading
import time

import harnesses
import hublayout as HL
import section_frame as SF
from theme import screen as _theme_screen  # fondo/tinta del tema

SUPPORTED = ('claude-code', 'codex', 'antigravity')
_NAMES = {'claude-code': 'Claude Code', 'codex': 'Codex', 'antigravity': 'Antigravity'}
_t = SF.t


def engine_name(d):
    eid = d.get('id') if isinstance(d, dict) else d
    return _NAMES.get(eid, str(eid))


def word():
    return HL.section_word('motores')


# ── datos ────────────────────────────────────────────────────────────────────
def _rows():
    return [d for d in harnesses.registry() if d.get('id') in SUPPORTED]


def users_of(eid):
    try:
        import agent_state
        return [a['display'] for a in agent_state.snapshot().registered() if a.get('engine') == eid]
    except Exception:
        return []


def initial():
    return {'engines': _rows(), 'engine': 0, 'msg': '', 'checks': {}, 'busy': False,
            'confirm': None, 'request': None}


def selected(S):
    rows = S.get('engines', [])
    return rows[S['engine'] % len(rows)] if rows else {}


def refresh(S, announce=True):
    """Re-detecta binarios (incluye PATH de una terminal nueva). No instala,
    no inicia sesión, no cambia asignaciones. Con una verificación en curso
    espera (su resultado no puede pegarse a un motor ya recargado)."""
    if S.get('busy'):
        S['msg'] = _t('motores.m.checking', 'verificando sesión…', 'checking sign-in…')
        return
    eid = selected(S).get('id')
    try:
        import path_refresh
        added = path_refresh.refresh()
    except Exception:
        added = []
    try:
        import agent_state
        agent_state.invalidate()
    except Exception:
        pass
    S['engines'] = _rows()
    S['engine'] = next((n for n, d in enumerate(S['engines']) if d['id'] == eid), 0)
    S['checks'] = {}
    S['confirm'] = None
    if announce:
        S['msg'] = _t('motores.m.reloaded', 'motores recargados', 'engines reloaded') + (
            ' · ' + _t('motores.m.path', 'PATH +{n} carpetas de una terminal nueva',
                       'PATH +{n} folders from a new terminal', n=len(added)) if added else '')


def m_enabled(eid):
    en = harnesses.enabled_ids()
    return (not en) or eid in en


def toggle_m(S):
    eid = selected(S).get('id')
    if not eid:
        return
    ids = [d['id'] for d in S.get('engines', [])]
    cur = harnesses.enabled_ids() or list(ids)
    new = [i for i in cur if i != eid] if eid in cur else cur + [eid]
    new = [i for i in ids if i in new]
    res = harnesses.set_enabled([] if set(new) == set(ids) else new)
    if res.get('ok'):
        S['msg'] = '✓ ' + (_t('motores.m.m_on', '{n} aparece en la tecla M del hub', '{n} shows up on the hub M key', n=_NAMES[eid])
                           if eid in new else
                           _t('motores.m.m_off', '{n} ya no aparece en la tecla M', '{n} no longer shows on the M key', n=_NAMES[eid]))
    else:
        S['msg'] = '✗ ' + str(res.get('error') or _t('motores.m.save_fail', 'no se pudo guardar',
                                                     "couldn't save"))


def check_login(S):
    """Verificación EXPLÍCITA en segundo plano (puede correr el CLI)."""
    if S.get('busy'):
        return
    d = dict(selected(S))
    S['busy'] = True
    S['msg'] = _t('motores.m.checking', 'verificando sesión…', 'checking sign-in…')

    def worker():
        try:
            import dispatch
            mod = dispatch.load_engine(d['id'])
            st = mod.status() if hasattr(mod, 'status') else {}
            if not d.get('binaries_ok'):
                lab, ok = 'missing', False
            elif 'session_active' in st:
                ok = bool(st['session_active'])
                lab = 'verified' if ok else 'needs_login'
            else:
                lab, ok = 'unknown', False
            S['checks'][d['id']] = {'state': lab, 'at': time.time()}
            S['msg'] = session_label(lab)
        except Exception:
            S['msg'] = _t('motores.m.probe_failed', 'no pude verificar la sesión', 'could not check sign-in')
        finally:
            S['busy'] = False
    threading.Thread(target=worker, daemon=True).start()


def session_label(state):
    return {'verified': _t('motores.s.verified', 'verificada', 'verified'),
            'needs_login': _t('motores.s.needs', 'requiere iniciar sesión', 'sign-in required'),
            'unknown': _t('motores.s.unknown', 'el programa no informa', 'not reported by the program'),
            'missing': _t('motores.s.missing', 'instala primero', 'install first'),
            }.get(state, _t('motores.s.unchecked', 'sin verificar', 'not checked'))


def status_of(S, d):
    """(texto corto, color-key) del estado del motor para la lista."""
    if not d.get('binaries_ok'):
        return _t('motores.l.missing', 'no instalado', 'not installed'), 'ERR'
    st = (S['checks'].get(d['id']) or {}).get('state')
    if st == 'verified':
        return _t('motores.l.ready', 'listo', 'ready'), 'OK'
    if st == 'needs_login':
        return _t('motores.l.login', 'falta sesión', 'needs sign-in'), 'ERR'
    return _t('motores.l.installed', 'instalado', 'installed'), 'DIM'


# ── render ───────────────────────────────────────────────────────────────────
def pares(S=None):
    return (('↑↓', _t('motores.k.pick', 'elige', 'pick')),
            ('Enter', _t('motores.k.next', 'instala / sesión', 'install / sign in')),
            ('v', _t('motores.k.verify', 'verifica', 'verify')),
            ('m', _t('motores.k.m', 'tecla M', 'M key')),
            ('r', _t('motores.k.reload', 'recarga', 'reload')),
            ('q', _t('motores.k.back', 'vuelve', 'back')))


def _left(S, K):
    def build(iw, ih):
        out = []
        for i, d in enumerate(S['engines']):
            txt, ck = status_of(S, d)
            mark = '%s%s%s' % (K['OK'] if d.get('binaries_ok') else K['ERR'],
                               '◆' if d.get('binaries_ok') else '◇', K['R'])
            out.append(SF.row(K, engine_name(d), txt, iw, sel=(i == S['engine']),
                              mark=mark, value_col=K[ck] if ck != 'DIM' else None))
        return out
    return build


def _right(S, K):
    def build(iw, ih):
        d = selected(S)
        eid = d.get('id')
        out = []
        try:
            import engine_install
            rec = engine_install.recipe(eid)
            miss = engine_install.missing_prereqs(rec)
        except Exception:
            rec, miss = None, []
        if S.get('confirm') == eid and rec:
            out += SF.text(K, _t('motores.c.title', '¿Instalar {n}?', 'Install {n}?', n=engine_name(d)),
                           iw, K['C'] + K['BO'])
            out.append('')
            out += SF.text(K, ' '.join(rec['cmd']), iw, K['WH'], max_lines=3)
            out += SF.text(K, _t('motores.c.src', 'fuente oficial: {u}', 'official source: {u}', u=rec['source']),
                           iw, K['DIM'], max_lines=2)
            if rec.get('note'):
                out += SF.text(K, rec['note'], iw, K['DIM'], max_lines=2)
            out.append('')
            out += SF.text(K, _t('motores.c.keys', 'Enter instala en esta terminal · Esc cancela',
                                 'Enter installs in this terminal · Esc cancels'), iw, K['C'])
            return out
        installed = bool(d.get('binaries_ok'))
        chk = (S['checks'].get(eid) or {}).get('state')
        if not installed:
            head = _t('motores.h.missing', 'No está instalado en esta máquina.', 'Not installed on this machine.')
            col = K['ERR']
        elif chk == 'verified':
            head = _t('motores.h.ready', 'Listo para usar.', 'Ready to use.')
            col = K['OK']
        else:
            head = _t('motores.h.installed', 'Instalado. La sesión no se ha verificado.',
                      'Installed. Sign-in not checked yet.')
            col = K['WH']
        out += SF.text(K, head, iw, col + K['BO'])
        out.append('')
        out.append(SF.kv(K, _t('motores.f.installed', 'instalado', 'installed'),
                         _t('motores.v.yes', 'sí', 'yes') if installed else _t('motores.v.no', 'no', 'no'), iw,
                         hint='' if installed else _t('motores.h.enter_install', 'Enter instala', 'Enter installs'),
                         value_col=K['OK'] if installed else K['ERR']))
        if installed:
            out.append(SF.kv(K, _t('motores.f.session', 'sesión', 'sign-in'), session_label(chk), iw,
                             hint=_t('motores.h.v', 'v verifica · Enter login', 'v checks · Enter sign-in')))
        out.append(SF.kv(K, _t('motores.f.m', 'tecla M', 'M key'),
                         _t('motores.v.yes', 'sí', 'yes') if m_enabled(eid) else _t('motores.v.no', 'no', 'no'),
                         iw, hint=_t('motores.h.m', 'm cambia', 'm toggles')))
        users = users_of(eid)
        out.append(SF.kv(K, _t('motores.f.users', 'lo usan', 'used by'),
                         ', '.join(users) if users else '—', iw))
        if not installed and miss:
            out.append('')
            out += SF.text(K, _t('motores.miss', 'Para instalarlo falta: {m}', 'To install it you need: {m}',
                                 m=', '.join(miss)), iw, K['ERR'], max_lines=2)
        out.append('')
        out += SF.bullets(K, [
            _t('motores.b1', 'Workspace usa el programa oficial; tu cuenta la gestiona él, no Workspace',
               'Workspace runs the official program; it manages your account, not Workspace'),
            _t('motores.b2', 'r recarga si lo instalaste desde otra terminal',
               'r reloads if you installed it from another terminal'),
            _t('motores.b3', 'el motor de cada agente se elige en Agentes (m)',
               "each agent's engine is chosen in Agents (m)"),
        ], iw)
        return out
    return build


def render(S, w, h):
    K = SF.K()
    sub = _t('motores.sub', 'motores — los programas que corren a tus agentes',
             'engines — the programs that run your agents')
    if not S.get('engines'):
        return SF.frame(K, w, h, sub, word(), pares(S), 'MOTORES', SF.text(K, '—', 40), '—', [],
                        msg=S.get('msg', ''))
    S['engine'] %= len(S['engines'])
    return SF.frame(K, w, h, sub, word(), pares(S),
                    _t('motores.box', 'MOTORES', 'ENGINES'), _left(S, K),
                    engine_name(selected(S)).upper(), _right(S, K), msg=S.get('msg', ''),
                    cursor_line=S['engine'], focus_left=not S.get('confirm'))


# ── acciones ─────────────────────────────────────────────────────────────────
def _enter(S):
    d = selected(S)
    eid = d.get('id')
    if not d.get('binaries_ok'):
        try:
            import engine_install
            rec = engine_install.recipe(eid)
            miss = engine_install.missing_prereqs(rec)
        except Exception:
            rec, miss = None, []
        if not rec:
            S['msg'] = _t('motores.m.norecipe', 'sin instalador oficial registrado', 'no official installer registered')
        elif miss:
            S['msg'] = '✗ ' + _t('motores.miss', 'Para instalarlo falta: {m}', 'To install it you need: {m}',
                                 m=', '.join(miss))
        elif S.get('confirm') == eid:
            S['confirm'] = None
            S['request'] = ('install', eid, rec['cmd'])
            return False
        else:
            S['confirm'] = eid
        return True
    try:
        import engine_install
        login = engine_install.recipe(eid)['login_cmd']
    except Exception:
        login = []
    if login:
        S['request'] = ('login', eid, login)
        return False
    return True


def act(S, key):
    """True = sigue · False = sale del loop (volver o correr un comando)."""
    if S.get('confirm'):
        if key in ('\r', '\n'):
            return _enter(S)
        S['confirm'] = None
        S['msg'] = _t('motores.m.cancel', 'cancelado · nada se instaló', 'cancelled · nothing installed')
        return True
    if key in ('q', 'Q', '\x1b', '\x03'):
        return False
    if not S.get('engines'):
        if key == 'r':
            refresh(S)
        return True
    S['msg'] = '' if not S.get('busy') else S['msg']
    n = len(S['engines'])
    if key in ('up', 'down', 'tab'):
        S['engine'] = (S['engine'] + (-1 if key == 'up' else 1)) % n
    elif key in ('\r', '\n'):
        return _enter(S)
    elif key == 'v':
        check_login(S)
    elif key == 'm':
        toggle_m(S)
    elif key == 'r':
        refresh(S)
    return True


# ── loop ─────────────────────────────────────────────────────────────────────
def _size(out):
    try:
        sz = os.get_terminal_size(out.fileno())
        return sz.columns, sz.lines
    except (OSError, AttributeError, ValueError):
        return 110, 44


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
    while True:
        S['request'] = None
        _loop(S)
        req = S.get('request')
        if not req:
            return
        kind, eid, cmd = req
        import subprocess
        print('\n  $ ' + ' '.join(cmd) + '\n')
        try:
            rc = subprocess.run(cmd, check=False).returncode
        except (OSError, KeyboardInterrupt) as e:
            rc = getattr(e, 'errno', 1) or 1
        try:
            input('\n' + _t('motores.m.return', 'Enter para volver a Motores', 'Enter to return to Engines'))
        except EOFError:
            pass
        refresh(S, announce=False)
        if kind == 'install':
            try:
                import engine_install
                why = engine_install.diagnose_exit(engine_install.recipe(eid), rc)
            except Exception:
                why = ''
            S['msg'] = ('✗ ' + why) if why else ('✓ ' + _t('motores.m.installed', '{n} instalado · ahora Enter para iniciar sesión',
                                                          '{n} installed · now Enter to sign in', n=_NAMES[eid]))
        else:
            S['msg'] = _t('motores.m.after_login', 'v verifica que la sesión quedó activa',
                          'v checks that the sign-in is active')


def _loop(S):
    import responsive_ui
    if os.name == 'nt':
        import msvcrt
        out = sys.stdout
        out.write('\033[?1049h\033[?25l')
        try:
            first, last = True, None
            while True:
                w, h = _size(out)
                frame = render(S, w, h)
                if frame != last:                  # repinta solo si cambió
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
                w, h = _size(out)
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
