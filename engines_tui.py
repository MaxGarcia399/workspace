"""WORKSPACE · engines_tui — sección MOTORES: qué motores tienes y cómo dejarlos listos.

REDISEÑO 2026-10-14 (concepto Omarchy): una caja centrada (section_box). A
la izquierda los motores con su estado (listo · sin sesión · no instalado);
a la derecha las opciones del elegido (en ventana angosta, debajo):
  instalar · ya lo instalé: recargar        (si no está instalado)
  sesión (Enter verifica) · iniciar sesión · aparece al cambiar de motor
→ entra a sus opciones, ↑↓ elige, Enter aplica, ← regresa. Instalar muestra
el comando y la fuente oficial y pide Enter otra vez. Qué agentes lo usan y
qué hace cada opción: en `i`. Workspace nunca ve tu cuenta.
"""
import os
import sys
import threading
import time

import harnesses
import hublayout as HL
import section_box as SB
import section_frame as SF
from theme import screen as _theme_screen  # fondo/tinta del tema

SUPPORTED = ('claude-code', 'codex', 'antigravity', 'opencode', 'openclaw', 'hermes')
_NAMES = {'claude-code': 'Claude Code', 'codex': 'Codex', 'antigravity': 'Antigravity',
          'opencode': 'OpenCode', 'openclaw': 'OpenClaw', 'hermes': 'Hermes'}
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


def initial(probe=True):
    """Al abrir, verifica la sesión de cada motor instalado EN SEGUNDO PLANO
    (no se quedan en «sin verificar»: eso hacía ver mal al producto)."""
    S = {'engines': _rows(), 'engine': 0, 'msg': '', 'checks': {}, 'busy': False,
         'confirm': None, 'request': None}
    if probe:
        verify_all(S)
    return S


#: Resultado reciente por motor: (momento, True/False/None). Volver a entrar a
#: Motores dentro de este plazo no vuelve a preguntar.
_SESSION_CACHE = {}
_SESSION_TTL = 60.0


#: Motores cuyo `status()` sabe más que «hay sesión»: falta elegir modelo o
#: activar el proveedor (`model_ready`), o un bloqueo de versión. Sin esto,
#: Motores decía «listo» y el agente abría en el asistente del motor.
_STATUS_ENGINES = ('openclaw', 'hermes')


def _probe(eid):
    """True/False/None (no se pudo saber) con el comando OFICIAL de cada motor,
    o 'needs_model' / 'version' cuando el motor tiene sesión pero no puede
    trabajar todavía."""
    hit = _SESSION_CACHE.get(eid)
    if hit and time.time() - hit[0] < _SESSION_TTL:
        return hit[1]
    try:
        import dispatch
        mod = dispatch.load_engine(eid)
        if eid in _STATUS_ENGINES and callable(getattr(mod, 'status', None)):
            st = mod.status() or {}
            if st.get('version_problem'):
                val = 'version'
            elif st.get('session_active') is True and st.get('model_ready') is False:
                val = 'needs_model'
            else:
                val = st.get('session_active')
        else:
            fn = getattr(mod, 'session_active', None)
            val = fn() if fn else None
        val = val if isinstance(val, bool) or val in ('needs_model', 'version') else None
    except Exception:
        val = None
    _SESSION_CACHE[eid] = (time.time(), val)
    return val


def verify_all(S, force=False):
    """Lanza la verificación de cada motor instalado (un hilo por motor).
    WORKSPACE_NO_SESSION_PROBE=1 la apaga (la suite de tests: jamás corre los
    programas reales)."""
    if os.environ.get('WORKSPACE_NO_SESSION_PROBE'):
        return
    for d in S.get('engines', []):
        if d.get('binaries_ok'):
            verify(S, d['id'], force=force)


def verify(S, eid, force=False):
    if force:
        _SESSION_CACHE.pop(eid, None)
    S['checks'][eid] = {'state': 'checking', 'at': time.time()}

    def worker():
        val = _probe(eid)
        S['checks'][eid] = {'state': {True: 'verified', False: 'needs_login',
                                      'needs_model': 'needs_model',
                                      'version': 'version'}.get(val, 'unknown'),
                            'at': time.time()}
        S.setdefault('versions', {})[eid] = version_of(eid)
    threading.Thread(target=worker, daemon=True).start()


def version_of(eid):
    """La cara del sistema de versiones para el socio (política «la más nueva
    por defecto» + Vigía, 2026-10-16) → {'st', 'have', 'rango', 'why', 'hint'}
    o None. Solo los motores que declaran VERIFIED_VERSIONS (opencode,
    OpenClaw, Hermes): Claude, Codex y Antigravity no dependen de la versión.
    `--version` sale de la caché en disco de engine_versions (12 h)."""
    try:
        import shutil
        import dispatch
        import engine_versions as EV
        mod = dispatch.load_engine(eid)
        if not getattr(mod, 'VERIFIED_VERSIONS', None):
            return None
        exe = shutil.which(getattr(mod, 'BINARY', '') or '')
        if not exe:
            return None
        v = EV.installed_version(exe)
        st, have, rango = EV.drift(mod, v)
        if not have:
            return None
        b = (EV.broken(mod, v) or {}) if st == 'broken' else {}
        return {'st': st, 'have': have, 'rango': rango, 'why': b.get('why', ''),
                'hint': b.get('hint', '') or (getattr(mod, 'UPGRADE_HINT', '')
                                              if st == 'unsupported' else '')}
    except Exception:
        return None


def version_label(info):
    """(texto, color-key) de la fila «versión». Cabe en la columna de
    opciones (≤20 visibles con una versión como 2026.10.12); el porqué va en
    Enter (version_note) y en `i`."""
    st, have = info.get('st'), info.get('have')
    if st == 'ok':
        return _t('motores.v.ok', '{v} · probada', '{v} · tested', v=have), 'OK'
    if st == 'newer':
        return _t('motores.v.newer', '{v} · nueva', '{v} · newer', v=have), 'DIM'
    if st == 'older':
        return _t('motores.v.older', '{v} · vieja', '{v} · older', v=have), 'DIM'
    if st == 'unsupported':
        return _t('motores.v.unsup', '{v} · muy vieja', '{v} · too old', v=have), 'ERR'
    if st == 'broken':
        return _t('motores.v.broken', '{v} · con falla', '{v} · known bug', v=have), 'ERR'
    return have, 'DIM'


def version_note(info):
    """Enter sobre «versión»: el porqué en una línea."""
    st = info.get('st')
    if st == 'broken':
        return '✗ %s%s' % (info.get('why') or '', (' — ' + info['hint']) if info.get('hint') else '')
    if st == 'unsupported':
        return '✗ ' + _t('motores.v.n_unsup', 'Workspace necesita {r}', 'Workspace needs {r}',
                         r=info.get('rango')) + ((' — ' + info['hint']) if info.get('hint') else '')
    if st == 'newer':
        return _t('motores.v.n_newer',
                  'lo normal: Workspace usa la más nueva; la verificada es {r} y la nueva se prueba '
                  'sola a diario · si algo falla, `workspace update` trae el ajuste',
                  "that's normal: Workspace uses the newest; {r} is verified and the new one is "
                  'tested daily · if something breaks, `workspace update` brings the fix',
                  r=info.get('rango'))
    if st == 'older':
        return _t('motores.v.n_older', 'verificadas: {r} · actualiza el motor desde su instalador oficial',
                  "verified: {r} · update the engine with its official installer", r=info.get('rango'))
    return _t('motores.v.n_ok', 'probada con Workspace (verificadas: {r})',
              'tested with Workspace (verified: {r})', r=info.get('rango'))


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
    verify_all(S, force=True)             # recién instalado o con sesión nueva
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
        S['msg'] = '✓ ' + (_t('motores.m.m_on', '{n} aparece al cambiar de motor en el hub (←→)', '{n} shows up when switching engines in the hub (←→)', n=_NAMES[eid])
                           if eid in new else
                           _t('motores.m.m_off', '{n} ya no aparece al cambiar de motor en el hub (←→)', '{n} no longer shows up when switching engines in the hub (←→)', n=_NAMES[eid]))
    else:
        S['msg'] = '✗ ' + str(res.get('error') or _t('motores.m.save_fail', 'no se pudo guardar',
                                                     "couldn't save"))


def check_login(S):
    """Enter sobre «sesión»: vuelve a preguntarle al programa (sin caché)."""
    d = selected(S)
    if d.get('binaries_ok'):
        verify(S, d['id'], force=True)
        S['msg'] = _t('motores.m.checking', 'verificando sesión…', 'checking sign-in…')


def session_label(state):
    return {'verified': _t('motores.s.active', 'activa', 'active'),
            'needs_login': _t('motores.s.none', 'no iniciada', 'not signed in'),
            'unknown': _t('motores.s.cant', 'no se pudo verificar', "couldn't check"),
            'missing': _t('motores.s.missing', 'instala primero', 'install first'),
            'needs_model': _t('motores.s.model', 'falta elegir modelo', 'choose a model'),
            'version': _t('motores.s.version', 'revisa la versión (i)', 'check the version (i)'),
            }.get(state, _t('motores.s.checking', 'verificando…', 'checking…'))


def status_of(S, d):
    """(texto corto, color-key) del estado del motor para la lista: si está
    listo para usarse se dice; si no, por qué."""
    if not d.get('binaries_ok'):
        return _t('motores.l.missing', 'no instalado', 'not installed'), 'ERR'
    st = (S['checks'].get(d['id']) or {}).get('state')
    if st == 'verified':
        return _t('motores.l.ready', 'listo', 'ready'), 'OK'
    if st == 'needs_login':
        return _t('motores.l.login2', 'sin sesión', 'not signed in'), 'ERR'
    if st == 'needs_model':
        return _t('motores.l.model', 'falta modelo', 'no model'), 'ERR'
    if st == 'version':
        return _t('motores.l.version', 'revisar versión', 'check version'), 'ERR'
    if st == 'checking' or st is None:
        return _t('motores.l.checking', 'verificando…', 'checking…'), 'DIM'
    return _t('motores.l.installed', 'instalado', 'installed'), 'DIM'


# ── REDISEÑO 2026-10-14 (concepto Omarchy): la cajita ─────────────────────
# A la izquierda la lista de motores │ a la derecha las opciones del elegido
# (instalar / ya lo instalé · sesión · iniciar sesión · ofrecer en el hub).
# La flecha va al final de la fila elegida, no en la división. → entra a sus
# opciones, ↑↓ elige, Enter actúa, ← regresa. En una ventana angosta las
# columnas no caben: la lista va arriba y las opciones abajo. Qué es un
# motor, quién lo usa y qué hace cada opción: en `i`.
LIST_W = 30
DETAIL_W = 42


def options(S, d):
    """[(clave, etiqueta, valor)] del motor: valor True/False = interruptor;
    texto = estado; "" = acción (›)."""
    eid = d.get('id')
    if not d.get('binaries_ok'):
        return [('install', _t('motores.o.install', 'instalar', 'install'), ''),
                ('reload', _t('motores.o.reload', 'ya lo instalé: recargar', 'I installed it: reload'), '')]
    chk = (S['checks'].get(eid) or {}).get('state')
    out = [('session', _t('motores.f.session', 'sesión', 'sign-in'), session_label(chk))]
    ver = (S.get('versions') or {}).get(eid)
    if ver:
        out.append(('version', _t('motores.f.version', 'versión', 'version'), version_label(ver)[0]))
    if chk not in ('verified', 'needs_model'):     # con sesión pero sin modelo: «cuenta y proveedor»
        out.append(('login', _t('motores.o.login', 'iniciar sesión', 'sign in'), ''))
    # SIEMPRE disponible: el flujo oficial del motor para entrar, cambiar de
    # cuenta o conectar proveedor. Workspace no guarda llaves ni tiene un
    # sistema de providers: solo abre la configuración del propio motor.
    out.append(('account', _t('motores.o.account', 'cuenta y proveedor',
                              'account and provider'), ''))
    out.append(('hub', _t('motores.o.hub3', 'ofrecer en el hub', 'offer in the hub'),
                m_enabled(eid)))
    return out


_ACCIONES = ('install', 'reload', 'login', 'account')


def _chips(S):
    if S.get('confirm'):
        return (('Enter', _t('motores.k.install', 'instala', 'install')),
                ('Esc', _t('motores.k.cancel', 'cancela', 'cancel')))
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
    if S.get('confirm') == eid:
        try:
            import engine_install
            rec = engine_install.recipe(eid)
        except Exception:
            rec = None
        out = [HL.clip('%s%s%s' % (K['C'] + K['BO'], _t('motores.c.title', '¿Instalar {n}?',
                                                         'Install {n}?', n=engine_name(d)), K['R']), iw), '']
        if rec:
            out += ['%s%s%s' % (K['WH'], ln, K['R']) for ln in SB._wrap(' '.join(rec['cmd']), iw)[:3]]
            out += ['%s%s%s' % (K['DIM'], ln, K['R']) for ln in SB._wrap(
                _t('motores.c.src', 'fuente oficial: {u}', 'official source: {u}', u=rec['source']), iw)[:2]]
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
        else:
            st = (S['checks'].get(eid) or {}).get('state')
            vcol = K['OK'] if st == 'verified' else (K['ERR'] if st == 'needs_login' else K['DIM'])
            valor = '%s%s%s' % (vcol, val, K['R'])
        out.append(HL.clip('%s%s%s%s%s' % (cur, tinta, HL.pad(lab, lab_w), K['R'], valor), iw))
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


def info_blocks(S, K):
    d = selected(S)
    eid = d.get('id')
    users = users_of(eid)
    try:
        import engine_install
        miss = engine_install.missing_prereqs(engine_install.recipe(eid))
    except Exception:
        miss = []
    estado = status_of(S, d)[0]
    blocks = [('h', engine_name(d)),
              ('kv', [(_t('motores.f.status', 'estado', 'status'), estado),
                      (_t('motores.f.users', 'lo usan', 'used by'), ', '.join(users) if users else '—')])]
    if not d.get('binaries_ok') and miss:
        blocks.append(('dim', _t('motores.miss', 'Para instalarlo falta: {m}', 'To install it you need: {m}',
                                 m=', '.join(miss))))
    blocks += [
        ('gap',),
        ('flow', [(_t('motores.info.n1', 'tu agente', 'your agent'),
                   _t('motores.info.c1', 'su cerebro', 'its brain')),
                  (_t('motores.info.n2', 'el motor', 'the engine'),
                   _t('motores.info.c2', 'programa oficial', 'official program')),
                  (_t('motores.info.n3', 'tu cuenta', 'your account'),
                   _t('motores.info.c3', 'el proveedor', 'the vendor'))]),
        ('gap',),
        ('p', _t('motores.info.p1',
                 'Un motor es el programa oficial (Claude Code, Codex, Antigravity, OpenCode, OpenClaw o Hermes) que corre a tus '
                 'agentes con tu propia cuenta. Workspace nunca ve ni guarda tus credenciales. Al '
                 'cambiar de motor, la pestaña sigue igual: el nuevo recibe su memoria y lo último '
                 'que pasó en el anterior.',
                 'An engine is the official program (Claude Code, Codex, Antigravity, OpenCode, OpenClaw or Hermes) that runs your '
                 'agents with your own account. Workspace never sees or stores your credentials. When '
                 'you switch engines the tab carries on: the new one gets its memory and the latest '
                 'from the previous one.')),
        ('h', _t('motores.info.h_opts', 'sus opciones', 'its options')),
        ('kv', [(_t('motores.o.install', 'instalar', 'install'),
                 _t('motores.info.o_install', 'corre el instalador oficial (te muestra el comando antes)',
                    'runs the official installer (shows you the command first)')),
                (_t('motores.f.session', 'sesión', 'sign-in'),
                 _t('motores.info.o_session2', 'se revisa sola al abrir; Enter vuelve a preguntar',
                    'checked on its own when you open this; Enter asks again')),
                (_t('motores.f.version', 'versión', 'version'),
                 _t('motores.info.o_version',
                    'la instalada y si ya la probamos. Workspace usa siempre la más nueva: '
                    'cada versión nueva se prueba sola a diario y, si una falla, la siguiente '
                    'actualización de Workspace lo marca aquí (y te deja abrir igual)',
                    'the installed one and whether we tested it. Workspace always uses the '
                    'newest: each new version is tested daily and, if one breaks, the next '
                    'Workspace update flags it here (and still lets you open it)')),
                (_t('motores.o.login', 'iniciar sesión', 'sign in'),
                 _t('motores.info.o_login', 'abre el login del propio programa',
                    "opens the program's own sign-in")),
                (_t('motores.o.account', 'cuenta y proveedor', 'account and provider'),
                 _t('motores.info.o_account',
                    'siempre a mano: abre la configuración oficial de cuenta y proveedor '
                    'de ese motor (Workspace no guarda llaves)',
                    "always there: opens that engine's official account and provider "
                    "setup (Workspace stores no keys)")),
                (_t('motores.o.hub3', 'ofrecer en el hub', 'offer in the hub'),
                 _t('motores.info.o_hub', 'si ←→ en el hub lo ofrece al cambiar el motor de un agente',
                    "whether ←→ in the hub offers it when changing an agent's engine"))]),
        ('gap',),
        ('dim', _t('motores.info.marks2',
                   'listo = instalado y con tu sesión activa (se verifica al abrir con el comando '
                   'oficial de cada programa) · el de cada agente se elige en Agentes',
                   "ready = installed and signed in (checked on open with each program's official "
                   "command) · each agent's is chosen in Agents")),
    ]
    return blocks


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


def prepare_login(eid):
    """Antes del login / «cuenta y proveedor»: si el motor corre en un perfil
    propio que hay que crear (Hermes), su adapter lo prepara con el mecanismo
    oficial (`prepare_account`). → (listo, aviso). Falla-suave: sin hook, listo."""
    try:
        import importlib
        mod = importlib.import_module('engines.' + str(eid).replace('-', '_'))
        prep = getattr(mod, 'prepare_account', None)
        if not callable(prep):
            return True, ''
        ok, why = prep()
        if ok:
            return True, (why + '.') if why else ''
        return False, '✗ ' + (why or 'no pude preparar el perfil del motor')
    except Exception:
        return True, ''


def _account(S):
    """«cuenta y proveedor»: corre el flujo OFICIAL de cuenta/proveedor del
    motor (engine_install._ACCOUNT). Al volver, se re-verifica la sesión."""
    eid = selected(S).get('id')
    try:
        import engine_install
        cmd = engine_install.recipe(eid)['account_cmd']
    except Exception:
        cmd = []
    if cmd:
        S['request'] = ('login', eid, cmd)
        return False
    S['msg'] = _t('motores.m.no_account', 'este motor no tiene un flujo de cuenta conocido',
                  'this engine has no known account flow')
    return True


def _aplica(S):
    """Enter sobre la opción elegida."""
    key = options(S, selected(S))[S.get('opt', 0)][0]
    if key == 'account':
        return _account(S)
    if key in ('install', 'login'):
        return _enter(S)
    if key == 'reload':
        refresh(S)
    elif key == 'session':
        check_login(S)
    elif key == 'version':
        ver = (S.get('versions') or {}).get(selected(S).get('id'))
        S['msg'] = version_note(ver) if ver else ''
    elif key == 'hub':
        toggle_m(S)
    return True


def act(S, key):
    """True = sigue · False = sale del loop (volver o correr un comando)."""
    if S.get('confirm'):
        if key in ('\r', '\n'):
            return _enter(S)
        S['confirm'] = None
        S['msg'] = _t('motores.m.cancel', 'cancelado · nada se instaló', 'cancelled · nothing installed')
        return True
    if SB.info_key(S, key):
        return True
    if key == '\x03':
        return False
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
        ready, why = prepare_login(eid) if kind == 'login' else (True, '')
        if why:
            print('\n  ' + why)
        # sin perfil listo (Hermes) el aviso es el motivo, no «verificando…»;
        # si el programa no está o no arranca, se dice aquí y en la lista
        rc, problem = (launch(cmd) if ready else (1, why))
        if ready and problem:
            print('\n  ' + problem)
        try:
            input('\n' + _t('motores.m.return', 'Enter para volver a Motores', 'Enter to return to Engines'))
        except EOFError:
            pass
        refresh(S, announce=False)
        S['msg'] = after_message(S, kind, eid, rc, problem, ready)


def launch(cmd):
    """Corre un comando de Motores con la RUTA real del programa. En Windows los
    CLIs de npm (npm, opencode, openclaw, codex…) son atajos `.cmd` y por su
    nombre suelto `subprocess` no los encuentra: instalar, iniciar sesión y
    «cuenta y proveedor» fallaban sin decir por qué (auditoría 2026-10-16).
    → (código, problema): problema = '' si se ejecutó; si no, la razón para
    el socio y no se ejecutó nada."""
    import shutil
    import subprocess
    exe = shutil.which(cmd[0])
    if not exe:
        return None, _t('motores.m.notfound',
                        '✗ no encontré `{b}` en el PATH de esta terminal — no se ejecutó nada; '
                        'si ya lo instalaste, elige «ya lo instalé: recargar» o abre una terminal nueva',
                        "✗ couldn't find `{b}` on this terminal's PATH — nothing ran; if you "
                        "already installed it, choose «I installed it: reload» or open a new terminal",
                        b=cmd[0])
    print('\n  $ ' + ' '.join(cmd) + '\n')
    try:
        # instalar / iniciar sesión / «cuenta y proveedor» corren el CLI del
        # motor: sin las fichas que cargó el hub (Greptile, 2026-10-17)
        import secret_store
        return subprocess.run([exe] + list(cmd[1:]), check=False,
                              env=secret_store.engine_env()).returncode, ''
    except KeyboardInterrupt:
        return 130, ''
    except OSError as e:
        return None, _t('motores.m.cantopen', '✗ no pude abrir `{b}` ({e}) — no se ejecutó nada',
                        "✗ couldn't open `{b}` ({e}) — nothing ran", b=cmd[0], e=e)


def after_message(S, kind, eid, rc, problem, ready=True):
    """El aviso al volver a Motores: lo que pasó de verdad."""
    if problem:
        return problem
    if not ready:
        return S.get('msg') or ''
    if kind == 'install':
        try:
            import engine_install
            why = engine_install.diagnose_exit(engine_install.recipe(eid), rc)
        except Exception:
            why = ''
        if why:
            return '✗ ' + why
        # el foco va a la siguiente acción útil: conectar la cuenta
        ops = [o[0] for o in options(S, selected(S))]
        nxt = 'login' if 'login' in ops else ('account' if 'account' in ops else None)
        if nxt:
            S['focus'], S['opt'] = 'detail', ops.index(nxt)
        return '✓ ' + _t('motores.m.installed', '{n} instalado · Enter para conectar tu cuenta',
                         '{n} installed · Enter to connect your account', n=_NAMES[eid])
    if rc not in (0, None):
        return _t('motores.m.login_rc', 'el programa terminó con código {rc} · verificando sesión…',
                  'the program exited with code {rc} · checking sign-in…', rc=rc)
    return _t('motores.m.checking', 'verificando sesión…', 'checking sign-in…')


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


if __name__ == '__main__':
    run()
