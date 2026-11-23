"""WORKSPACE · engines_tui — sección MOTORES: qué motores tienes y cómo dejarlos listos.

REDISEÑO 2026-10-14 (concepto Omarchy): una caja centrada (section_box). A
la izquierda los motores con su estado (listo · sin sesión · no instalado);
a la derecha las opciones del elegido (en ventana angosta, debajo):
  instalar · ya lo instalé: recargar        (si no está instalado)
  sesión (Enter verifica) · iniciar sesión · aparece al cambiar de motor
→ entra a sus opciones, ↑↓ elige, Enter aplica, ← regresa. Instalar muestra
el comando y la fuente oficial y pide Enter otra vez. Qué agentes lo usan y
qué hace cada opción: en `i`. Workspace nunca ve tu cuenta.

F0.5 (22-nov): aquí solo queda el DIBUJO de la pantalla de antes. La lógica (qué motores hay, su sesión, instalar,
iniciar sesión, «cuenta y proveedor») vive en motores_logica, sin pantalla; este módulo la vuelve a exportar con los
mismos nombres durante una versión.
"""
import os
import shlex
import sys
import threading
import time

import harnesses
import hublayout as HL
import section_box as SB
import section_frame as SF
from theme import screen as _theme_screen  # fondo/tinta del tema

_t = SF.t

# ── la lógica vive en motores_logica (sin pantalla); aquí, los mismos nombres ──
# Un puente para una versión: quien importa engines_tui (o lo parcha en una prueba: mock.patch("engines_tui._probe"))
# sigue funcionando igual. Asignar uno de esos nombres aquí también lo asigna en motores_logica, así el parche llega a
# quien ya llama a motores_logica directamente.
import types as _types  # noqa: E402
import motores_logica as _ML  # noqa: E402

for _n in _ML.NOMBRES:
    globals()[_n] = getattr(_ML, _n)


class _Puente(_types.ModuleType):
    def __setattr__(self, k, v):
        if k in _ML.NOMBRES:
            setattr(_ML, k, v)
        super().__setattr__(k, v)


sys.modules[__name__].__class__ = _Puente


def word():
    return HL.section_word('motores')


# ── REDISEÑO 2026-10-14 (concepto Omarchy): la cajita ─────────────────────
# A la izquierda la lista de motores │ a la derecha las opciones del elegido
# (instalar / ya lo instalé · sesión · iniciar sesión · ofrecer en el hub).
# La flecha va al final de la fila elegida, no en la división. → entra a sus
# opciones, ↑↓ elige, Enter actúa, ← regresa. En una ventana angosta las
# columnas no caben: la lista va arriba y las opciones abajo. Qué es un
# motor, quién lo usa y qué hace cada opción: en `i`.
LIST_W = 30
DETAIL_W = 42


def _chips(S):
    if S.get('confirm'):
        return (('Enter', (_t('motores.k.repair', 'repara', 'repair')
                           if S.get('confirm_kind') == 'repair' else
                           _t('motores.k.reinstall', 'reinstala', 'reinstall'))
                 if S.get('confirm_cmds') else _t('motores.k.install', 'instala', 'install')),
                ('Esc', _t('motores.k.cancel', 'cancela', 'cancel')))
    if S.get('acct'):
        if S['acct'].get('confirm'):
            return (('Enter', _t('motores.k.confirm', 'confirma', 'confirm')),
                    ('Esc', _t('motores.k.cancel', 'cancela', 'cancel')))
        return (('↑↓', _t('motores.k.option', 'opción', 'option')),
                ('Enter', _t('motores.k.do', 'aplica', 'apply')),
                ('←', _t('motores.k.to_opts2', 'a sus opciones', 'to its options')))
    if S.get('focus') == 'detail':
        return (('↑↓', _t('motores.k.option', 'opción', 'option')),
                ('Enter', _t('motores.k.do', 'aplica', 'apply')),
                ('←', _t('motores.k.to_list', 'a la lista', 'to the list')),
                ('i', _t('motores.k.info', 'cómo funciona', 'how it works')))
    return (('↑↓', _t('motores.k.pick', 'elige', 'pick')),
            ('→', _t('motores.k.to_opts', 'sus opciones', 'its options')),
            ('i', _t('motores.k.info', 'cómo funciona', 'how it works')),
            ('q', _t('motores.k.back', 'vuelve', 'back')))


def _mark(S, d):
    """La palabra de estado de la lista (listo · sin sesión · no instalado ·
    verificando…), en su color."""
    return status_of(S, d)


def _detalle(S, K, d, iw):
    """Solo las opciones del motor (o la confirmación de instalar)."""
    eid = d.get('id')
    if S.get('confirm') == eid and S.get('confirm_cmds'):
        return _detalle_reinstall(S, K, d, iw), 0
    if (S.get('acct') or {}).get('eid') == eid:
        return _detalle_cuenta(S, K, d, iw)
    if S.get('confirm') == eid:
        try:
            import engine_install
            rec = engine_install.recipe(eid)
        except Exception:
            rec = None
        out = [HL.clip('%s%s%s' % (K['C'] + K['BO'], _t('motores.c.title', '¿Instalar {n}?',
                                                         'Install {n}?', n=engine_name(d)), K['R']), iw), '']
        if rec:                            # Windows: qué baja Workspace y qué corre
            for txt in engine_install.shown(rec['cmd']):
                out += ['%s%s%s' % (K['WH'], ln, K['R']) for ln in SB._wrap(txt, iw)[:3]]
            out += ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in SB._wrap(
                _t('motores.c.src', 'fuente oficial: {u}', 'official source: {u}', u=rec['source']), iw)[:2]]
            if rec.get('aviso'):           # el diálogo que va a salir, ANTES de Enter
                out.append('')
                out += ['%s%s%s' % (K['B'], ln, K['R']) for ln in SB._wrap(rec['aviso'], iw)[:4]]
        return out, 0
    activo = S.get('focus') == 'detail'
    ops = options(S, d)
    S['opt'] = max(0, min(S.get('opt', 0), len(ops) - 1))
    lab_w = max(HL.vis(o[1]) for o in ops if o[0] not in _ACCIONES) + 2 if any(
        o[0] not in _ACCIONES for o in ops) else 0
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
                                    _t('motores.v.yes', 'sí', 'yes') if val else _t('motores.v.no', 'no', 'no'),
                                    K['R'])
        elif key == 'version':
            valor = '%s%s%s' % (K[version_label(S['versions'][eid])[1]], val, K['R'])
        elif key == 'integration':
            valor = '%s%s%s' % (K[integration_label(integration_of(eid) or {})[1]], val, K['R'])
        else:
            st = (S['checks'].get(eid) or {}).get('state')
            vcol = K['OK'] if st == 'verified' else (
                K['ERR'] if st in ('needs_login', 'blocked', 'incomplete') else K['DIM'])
            valor = '%s%s%s' % (vcol, val, K['R'])
        out.append(HL.clip('%s%s%s%s%s' % (cur, tinta, HL.pad(lab, lab_w), K['R'], valor), iw))
    why = ((S.get('blocked') or {}).get(eid) or {}).get('why')
    if why and (S['checks'].get(eid) or {}).get('state') in ('blocked', 'incomplete'):
        out.append('')                    # la línea clara: qué pasa y qué hacer
        out += ['%s%s%s' % (K['ERR'], ln, K['R']) for ln in SB._wrap(why, iw)[:3]]
    elif any(o[0] == 'integration' for o in ops):
        info = integration_of(eid) or {}
        if info.get('level') == 'experimental':  # por qué «experimental», siempre a la vista
            out.append('')
            out += ['%s%s%s' % (K['DIM'], ln, K['R'])
                    for ln in SB._wrap(integration_note(info), iw)[:6]]
    return out, fila


def _detalle_reinstall(S, K, d, iw):
    """Confirmación de «reinstalar»: los comandos tal cual (quitar el cask de
    Homebrew y la receta oficial) y la fuente, antes de Enter."""
    try:
        import engine_install
        rec = engine_install.recipe(d.get('id')) or {}
    except Exception:
        rec = {}
    titulo = (_t('motores.c.repairtitle', '¿Reparar {n}?', 'Repair {n}?', n=engine_name(d))
              if S.get('confirm_kind') == 'repair' else
              _t('motores.c.retitle', '¿Reinstalar {n}?', 'Reinstall {n}?', n=engine_name(d)))
    out = [HL.clip('%s%s%s' % (K['C'] + K['BO'], titulo, K['R']), iw), '']
    for cmd in S.get('confirm_cmds') or []:
        for txt in engine_install.shown(cmd, lambda c: '$ ' + shlex.join(c)):
            out += ['%s%s%s' % (K['WH'], ln, K['R']) for ln in SB._wrap(txt, iw)[:3]]
    if rec.get('source'):
        out += ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in SB._wrap(
            _t('motores.c.src', 'fuente oficial: {u}', 'official source: {u}', u=rec['source']),
            iw)[:2]]
    return out


def _detalle_cuenta(S, K, d, iw):
    """«cuenta y proveedor» con sesión (o sin saber) en un motor que no tiene
    selector de modelo fuera del chat: el estado, dónde se elige el modelo y
    las acciones OFICIALES que declara su adapter (account_menu)."""
    A = S['acct']
    menu = A.get('menu') or {}
    acts = menu.get('actions') or []
    n = engine_name(d)
    out = [HL.clip('%s%s%s' % (K['C'] + K['BO'], _t('motores.a.title', '{n} · cuenta y proveedor',
                                                     '{n} · account and provider', n=n), K['R']),
                   iw)]
    if A.get('confirm') == 'switch':
        cmds = dict(acts).get('switch') or []
        out += ['', HL.clip('%s%s%s' % (K['WH'] + K['BO'], _t(
            'motores.a.sw_q', '¿Cambiar de cuenta en {n}?', 'Switch account in {n}?', n=n),
            K['R']), iw)]
        out += ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in SB._wrap(_t(
            'motores.a.sw_why', 'cierra tu sesión y abre el inicio de sesión oficial',
            'signs you out and opens the official sign-in'), iw)[:2]]
        for cmd in cmds:
            out += ['%s%s%s' % (K['WH'], ln, K['R']) for ln in SB._wrap('$ ' + shlex.join(cmd), iw)[:2]]
        return out, 0
    if A.get('active') is True:
        out.append(HL.clip('%s%s%s' % (K['OK'], _t('motores.a.on', '✓ sesión iniciada',
                                                     '✓ signed in'), K['R']), iw))
    elif (S['checks'].get(A.get('eid')) or {}).get('state') in (None, 'checking'):
        out.append(HL.clip('%s%s%s' % (K['DIM'], _t('motores.a.checking', 'sesión: verificando…',
                                                     'sign-in: checking…'), K['R']), iw))
    else:
        out.append(HL.clip('%s%s%s' % (K['DIM'], _t('motores.a.unknown',
                                                     'sesión: no se pudo verificar',
                                                     "sign-in: couldn't check"), K['R']), iw))
    out += ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in SB._wrap(account_note(menu, n), iw)[:2]]
    if menu.get('warn'):
        out += ['%s%s%s' % (K['ERR'], ln, K['R']) for ln in SB._wrap(menu['warn'], iw)[:5]]
    out.append('')
    A['opt'] = max(0, min(A.get('opt', 0), len(acts) - 1)) if acts else 0
    fila = len(out)
    for i, (key, _cmd) in enumerate(acts):
        on = i == A['opt']
        if on:
            fila = len(out)
        cur = ('%s%s %s' % (K['C'] + K['BO'], K['PTR'], K['R'])) if on else '  '
        tinta = (K['WH'] + K['BO']) if on else K['GREY']
        lab = _acct_label(key, d)
        flecha = '%s›%s' % ((K['C'] + K['BO']) if on else K['DK'], K['R'])
        out.append(HL.clip('%s%s%s%s%s%s' % (cur, tinta, lab, K['R'],
                                             ' ' * max(1, iw - 3 - HL.vis(lab)), flecha), iw))
    return out, fila


def _cuerpo(S, K, iw):
    """Lista de motores │ opciones del elegido (pedido del dueño: en Motores
    la división de izquierda a derecha). La flecha al final de la fila
    elegida dice hacia dónde lleva ←/→: ▸ abre sus opciones, ◂ regresa."""
    d = selected(S)
    der = S.get('focus') == 'detail' or bool(S.get('confirm'))
    items = [(engine_name(x),) + _mark(S, x) for x in S['engines']]
    sel = S['engine'] % len(S['engines'])
    tail = '◂' if der else '▸'
    if iw < LIST_W + SB.SPLIT_GAP + 26:
        # angosta: no caben dos columnas → la lista arriba, las opciones abajo
        arriba = SB.pick_list(K, items, sel, iw, min(len(items), 8), sel_tail=tail)
        opciones, fila = _detalle(S, K, d, iw)
        S['_cur'] = len(arriba) + 2 + fila if der else min(sel, len(arriba) - 1)
        etiqueta = '%s · %s' % (engine_name(d), _t('motores.opts', 'opciones', 'options'))
        return SB.stack(K, arriba, opciones, iw, label=etiqueta, active=der)
    opciones, fila = _detalle(S, K, d, iw - LIST_W - SB.SPLIT_GAP)
    izq = SB.pick_list(K, items, sel, LIST_W, max(len(opciones), min(len(items), 8)),
                       sel_tail=tail)
    S['_cur'] = fila if der else min(sel, len(izq) - 1)
    return SB.split(K, izq, opciones, iw, LIST_W)


def render(S, w, h):
    K = SF.K()
    titulo = _t('motores.box', 'MOTORES', 'ENGINES')
    if S.get('info') and S.get('engines'):
        return SB.info_frame(K, w, h, word(), _t('motores.info.title', 'CÓMO FUNCIONAN LOS MOTORES',
                                                  'HOW ENGINES WORK'),
                             info_blocks(S, K), state=S['info'], box_w=64)
    if not S.get('engines'):
        return SB.frame(K, w, h, word(), titulo, ['—'], _chips(S), msg=S.get('msg', ''), box_w=40)
    S['engine'] %= len(S['engines'])
    return SB.frame(K, w, h, word(), titulo, lambda iw: _cuerpo(S, K, iw), _chips(S),
                    msg=S.get('msg', ''), cursor_line=lambda: S.get('_cur', 0),
                    box_w=LIST_W + SB.SPLIT_GAP + DETAIL_W,
                    stable_rows=max(min(len(S['engines']), 8), 6))


# ── acciones ─────────────────────────────────────────────────────────────────


def _act_cuenta(S, key):
    """Teclas dentro del menú de cuenta. «cambiar de cuenta» pide confirmar
    (cierra la sesión); Esc/← regresa a las opciones del motor."""
    A = S['acct']
    acts = (A.get('menu') or {}).get('actions') or []
    S['msg'] = ''
    if A.get('confirm'):
        if key in ('\r', '\n'):
            return _account_do(S, A['confirm'])
        A['confirm'] = None
        S['msg'] = _t('motores.m.cancel2', 'cancelado · tu sesión sigue igual',
                      'cancelled · your sign-in is unchanged')
        return True
    if key in ('\x1b', 'left', 'q', 'Q'):
        S['acct'] = None
    elif key in ('up', 'down') and acts:
        A['opt'] = (A.get('opt', 0) + (-1 if key == 'up' else 1)) % len(acts)
    elif key in ('\r', '\n', ' ') and acts:
        k = acts[A.get('opt', 0) % len(acts)][0]
        if k == 'switch':
            A['confirm'] = 'switch'
            return True
        return _account_do(S, k)
    return True


def _aplica(S):
    """Enter sobre la opción elegida."""
    key = options(S, selected(S))[S.get('opt', 0)][0]
    if key == 'account':
        return _account(S)
    if key in ('reinstall', 'repair'):
        return _reinstall(S, key)
    if key in ('install', 'login'):
        return _enter(S)
    if key == 'reload':
        refresh(S)
    elif key == 'session':
        check_login(S)
    elif key == 'version':
        ver = (S.get('versions') or {}).get(selected(S).get('id'))
        S['msg'] = version_note(ver) if ver else ''
    elif key == 'integration':
        info = integration_of(selected(S).get('id'))
        S['msg'] = integration_note(info) if info else ''
    elif key == 'hub':
        toggle_m(S)
    return True


def act(S, key):
    """True = sigue · False = sale del loop (volver o correr un comando)."""
    if S.get('confirm'):
        if key in ('\r', '\n'):
            return _enter(S)
        S['confirm'], S['confirm_cmds'], S['confirm_kind'] = None, None, None
        S['msg'] = _t('motores.m.cancel', 'cancelado · nada se instaló', 'cancelled · nothing installed')
        return True
    if SB.info_key(S, key):
        return True
    if key == '\x03':
        return False
    if S.get('acct'):
        return _act_cuenta(S, key)
    if not S.get('engines'):
        if key == 'r':
            refresh(S)
        return key not in ('q', 'Q', '\x1b')
    S['msg'] = '' if not S.get('busy') else S['msg']
    n = len(S['engines'])
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
    if key in ('up', 'down', 'tab'):
        S['engine'] = (S['engine'] + (-1 if key == 'up' else 1)) % n
        S['opt'] = 0
    elif key in ('\r', '\n', 'right', ' '):
        S['focus'] = 'detail'
        S['opt'] = 0
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
def run(motor=None, accion=None, sesion=None):
    S = initial()
    indice = next((i for i, fila in enumerate(S["engines"]) if fila.get("id") == motor), None)
    if indice is not None:
        S["engine"] = indice
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
        if accion and indice is not None:
            # La ficha H-1 abre el mismo menú oficial y las mismas confirmaciones.
            if accion == "account":
                if selected(S).get("binaries_ok"):
                    _account(S, {"activa": True, "sin-sesion": False}.get(sesion))
                else:
                    S["msg"] = _t("motores.m.install_first", "Instala el motor primero.", "Install the engine first.")
            elif accion == "login":
                _enter(S)
            elif accion == "repair":
                _reinstall(S, "repair" if install_block(motor) else "reinstall")
            else:
                opciones = options(S, selected(S))
                opt = next((i for i, f in enumerate(opciones) if f[0] == accion), None)
                if opt is not None:
                    S["opt"] = opt
                    _aplica(S)
            accion = None
        if not S.get('request'):
            _loop(S)
        req = S.get('request')
        if not req:
            return
        kind, eid, cmd = req[:3]
        opts = req[3] if len(req) > 3 else {}
        rc, problem, ready = execute(kind, eid, cmd, opts)
        try:
            input('\n' + _t('motores.m.return', 'Enter para volver a Motores', 'Enter to return to Engines'))
        except EOFError:
            pass
        refresh(S, announce=False)
        S['msg'] = after_message(S, kind, eid, rc, problem, ready)


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
            crudo = termios.tcgetattr(fd)
            out.write('\033[?1049h\033[?25l')
            first, last = True, None
            while True:
                # red de seguridad: si un programa externo regresó la terminal
                # a modo normal, las teclas dejarían de llegar → recuperarlo
                if termios.tcgetattr(fd) != crudo:
                    tty.setraw(fd)
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


if __name__ == "__main__":
    # ARCHIVO MÍNIMO por una versión (se borra en la versión 2): esta pantalla ya no se abre. Quien la corre
    # directo, o un hub que quedó abierto durante la actualización, llega a lo nuevo (puertas.redirigir).
    import puertas
    sys.exit(puertas.redirigir('motores', sys.argv[1:]))
