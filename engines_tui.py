"""Engine transparency screen. Uses the registry and existing connection guides."""
import os
import sys
import textwrap
import threading
import time

import agents_tui as A
import hublayout as HL
import harnesses
import brain_view
import i18n

SECTIONS = ('status', 'features', 'continuity', 'providers')
GUIDES = {
    'claude-code': 'https://code.claude.com/docs/en/setup',
    'codex': 'https://learn.chatgpt.com/docs/codex/cli',
    'antigravity': 'https://www.antigravity.google/docs/cli/install/',
}


def t(key, **kw):
    return i18n.t('engines.' + key, **kw)


def initial():
    return {'engines': [d for d in harnesses.registry() if d.get('id') in SUPPORTED], 'engine': 0, 'sec': 0, 'row': 0,
            'offset': 0, 'msg': '', 'request': None, 'checks': {}, 'busy': False,
            'agents': A.initial().get('agents', []), 'agent': 0, 'view': 'catalog', 'action': 0}


def selected(S):
    rows = S.get('engines', [])
    return rows[S['engine'] % len(rows)] if rows else {}


def cfg(S):
    rows = S.get('agents', [])
    return rows[S['agent'] % len(rows)] if rows else {}


def _features(d):
    caps = d.get('capabilities', {})
    return [(t('cap.' + key), t('value.' + str(caps.get(key, False)).lower()),
             t('why.' + key)) for key in
            ('launch', 'inject_context', 'mcp', 'hooks', 'sessions',
             'statusline', 'status_live', 'headless')]


SUPPORTED = ('claude-code', 'codex', 'antigravity')
FEATURE_KEYS = ('launch', 'inject_context', 'mcp', 'hooks', 'sessions',
                'statusline', 'status_live', 'headless')


def engine_name(d):
    return {'claude-code': 'Claude Code', 'codex': 'Codex',
            'antigravity': 'Gemini · Antigravity'}.get(d.get('id'), d.get('name', ''))


def providers():
    # The interactive catalog contains adapters we ship, not API profile files.
    return [{'name': {'claude-code': 'anthropic', 'codex': 'codex',
                       'antigravity': 'antigravity'}[d['id']],
             'engine': d['id'], 'display': engine_name(d),
             'connection': 'official_cli', 'auth': 'oauth', 'cost': 'unknown',
             'present': bool(d.get('binaries_ok'))}
            for d in harnesses.registry() if d.get('id') in SUPPORTED]


def setup_steps(S):
    d = selected(S)
    state = (S.get('connect') or {}).get('connect') or {}
    provider = state.get('provider')
    eid = {'anthropic': 'claude-code', 'codex': 'codex',
           'antigravity': 'antigravity'}.get(provider, d.get('id'))
    if provider:
        d = next((x for x in S['engines'] if x.get('id') == eid), d)
    installed = bool((state.get('status') or {}).get('cli_present')) if provider else bool(d.get('binaries_ok'))
    verified = S['checks'].get(eid, {}).get('verified', False)
    agent = cfg(S)
    binding, _ = harnesses.binding(agent.get('name', ''), agent.get('engine', ''))
    return [(t('binary'), installed), (t('login'), verified),
            (t('assignment'), bool(agent) and binding == eid)]


def concept_map(S, K, width, height):
    sec = SECTIONS[S['sec']]
    if sec == 'status':
        return status_graph(S, K, width, height)
    if S.get('connect') or sec == 'status':
        steps = setup_steps(S)
        result = [K['C'] + K['BO'] + t('setup.title') + K['R'], '']
        for n, (label, done) in enumerate(steps, 1):
            result.append((K['OK'] if done else K['DIM']) +
                          ('◆ ' if done else '◇ ') + str(n) + '  ' + label +
                          '  ·  ' + t('step.done' if done else 'step.pending') + K['R'])
        result += ['', t('setup.note')]
    elif sec == 'features':
        key = FEATURE_KEYS[S['row'] % len(FEATURE_KEYS)]
        return capability_graph(S, K, width, height)
    elif sec == 'continuity':
        stages = ('capture', 'checkpoint', 'retrieve', 'distill')
        focus = S['row'] % len(stages)
        result = [K['C'] + K['BO'] + t('continuity.title') + K['R'], '']
        for n, stage in enumerate(stages):
            result.append((K['C'] + K['BO'] if n == focus else K['DIM']) +
                          ('◆ ' if n == focus else '◇ ') + t(stage) + K['R'])
            result.append('    ' + t('flow.' + stage))
    else:
        result = [K['C'] + K['BO'] + t('provider.map') + K['R'], '',
                  t('node.brain') + ' → Workspace → ' + t('connection.official_cli'),
                  '                         ↓', t('provider.account'), '', t('provider.scope')]
    if width >= 70 and height >= 6:
        if S.get('connect') or sec == 'status':
            nodes = tuple((('◆ ' if done else '◇ ') + label, 'ok' if done else 'dk')
                          for label, done in setup_steps(S))
            note = t('setup.note')
        elif sec == 'continuity':
            stages = ('capture', 'checkpoint', 'retrieve', 'distill')
            nodes = tuple((t(stage), 'c' if n == S['row'] % 4 else 'dk')
                          for n, stage in enumerate(stages))
            note = t('flow.' + stages[S['row'] % 4])
        else:
            rows = providers()
            provider = rows[S['row'] % len(rows)]['display'] if rows else engine_name(selected(S))
            nodes = ((t('node.brain'), 'b2'), ('Workspace', 'c'), (provider, 'b'))
            note = t('provider.account')
        graph = brain_view.pipeline(HL, K, A._mk, width, height, nodes,
                                    ('',) * (len(nodes) - 1), note)
        if graph is not None:
            return graph
    out = []
    for line in result:
        # Wrap plain explanations; preserve ANSI headings as complete clipped lines.
        out += [HL.clip(line, width)] if '\033' in line else textwrap.wrap(line, max(10, width)) or ['']
    return out[:height]


def status_model(S):
    d = dict(selected(S))
    wizard = (S.get('connect') or {}).get('connect') or {}
    if wizard:
        eid = {'anthropic': 'claude-code', 'codex': 'codex',
               'antigravity': 'antigravity'}.get(wizard.get('provider'))
        d = dict(next((row for row in S['engines'] if row.get('id') == eid), d))
        if 'cli_present' in (wizard.get('status') or {}):
            d['binaries_ok'] = bool(wizard['status']['cli_present'])
    eid = d.get('id')
    name = engine_name(d)
    agent = cfg(S)
    who = agent.get('display') or agent.get('name') or '—'
    binding, _ = harnesses.binding(agent.get('name', ''), agent.get('engine', ''))
    current = engine_name({'id': binding, 'name': binding})
    check = S['checks'].get(eid, {})
    login = check.get('label', t('unverified'))
    installed = t('installed') if d.get('binaries_ok') else t('missing')
    focus = S['row'] % 4
    if focus == 0:
        nodes = ((name, 'c'), (installed, 'ok' if d.get('binaries_ok') else 'dk'),
                 (t('status.open_guide'), 'b'))
        caps = (t('status.machine'), 'Enter')
        details = [t('binary'), installed, t('binaries', names=', '.join(d.get('needs', []))), t('status.install_note')]
    elif focus == 1:
        nodes = ((name, 'c'), (t('status.probe'), 'b'),
                 (login, 'ok' if check.get('verified') else 'dk'))
        caps = ('v', t('status.evidence'))
        details = [t('login'), t('login_state', state=login), t('status.login_note')]
    elif focus == 2:
        nodes = ((who + ': ' + current, 'b2'), (name, 'c'),
                 (t('status.next_launch'), 'b'))
        caps = ('u', t('status.saved'))
        details = [t('assignment'), t('binding', name=who, engine=current),
                   t('status.assignment_action', engine=name), t('status.assignment_note')]
    else:
        nodes = (('Workspace', 'c'), (t('guide'), 'b2'),
                 (t('status.install_login'), 'b'))
        caps = ('Enter', name)
        details = [t('guide'), GUIDES.get(eid, t('no_guide')), t('status.guide_note')]
    return nodes, caps, details


def status_graph(S, K, width, height):
    nodes, caps, details = status_model(S)
    canvas = A._mk(K, width, height)
    canvas.put(0, 0, '◆ ' + details[0].upper(), K['C'] + K['BO'], width)
    # Use compact labels only when full labels do not fit the horizontal graph.
    graph = brain_view.pipeline(HL, K, A._mk, width, max(6, height - 2),
                                nodes, caps, '')
    if graph is not None:
        lines = [K['C'] + K['BO'] + '◆ ' + details[0].upper() + K['R'], ''] + graph
        notes = textwrap.wrap(details[-1], max(10, width - 4))
        for n, line in enumerate(notes):
            if 7 + n < height:
                lines[7 + n] = K['DIM'] + '  ' + line + K['R']
        return lines[:height]
    else:
        # A vertical graph retains every state on narrower screens.
        box_w = min(width, 52)
        x = max(0, (width - box_w) // 2)
        colors = {'c': K['C'], 'ok': K['OK'], 'dk': K['DIM'], 'b': K['B'], 'b2': K['B2']}
        for n, (label, color) in enumerate(nodes):
            y = 1 + n * 4
            if y + 2 >= height:
                break
            brain_view.box(canvas, K, x, y, box_w, label, colors[color])
            if n < len(nodes) - 1 and y + 3 < height:
                canvas.put(x + box_w // 2, y + 3, '↓ ' + caps[n], K['C'], box_w // 2)
        note_y = 13
    for n, line in enumerate(textwrap.wrap(details[-1], max(10, width - 4))):
        if note_y + n < height:
            canvas.put(2, note_y + n, line, K['DIM'], width - 4)
    return canvas.lines()


def capability_graph(S, K, width, height):
    """Explain one integration without growing with the engine catalog."""
    d = selected(S)
    key = FEATURE_KEYS[S['row'] % len(FEATURE_KEYS)]
    value = d.get('capabilities', {}).get(key, False)
    route = t('route.' + key + '.' + str(value).lower())
    # Each actual stage gets its own node; unsupported integrations end explicitly.
    stages = [part.strip() for part in route.split('→')]
    labels = [engine_name(d)] + stages
    nodes = tuple((label, 'c' if n == 0 else 'dk' if value is False else 'b2')
                  for n, label in enumerate(labels))
    title = '◆ ' + engine_name(d) + ' · ' + t('cap.' + key)
    graph = brain_view.pipeline(HL, K, A._mk, width, max(6, height - 2),
                                nodes, ('',) * (len(nodes) - 1), '')
    if graph is not None:
        lines = [K['C'] + K['BO'] + title + K['R'], ''] + graph
        note_y = 6
    else:
        canvas = A._mk(K, width, height)
        canvas.put(0, 0, title, K['C'] + K['BO'], width)
        # Two columns keep stages readable when a horizontal chain will not fit.
        box_w = max(12, (width - 5) // 2)
        for n, (label, color) in enumerate(nodes):
            x = 0 if n % 2 == 0 else box_w + 5
            y = 2 + (n // 2) * 4
            if y + 2 >= height:
                break
            col = K['C'] if color == 'c' else K['DIM'] if color == 'dk' else K['B2']
            brain_view.box(canvas, K, x, y, box_w, label, col)
            if n % 2 == 0 and n + 1 < len(nodes):
                canvas.put(x + box_w - 1, y + 1, '├──→', col)
            elif n + 1 < len(nodes) and y + 3 < height:
                canvas.put(0, y + 3, '↓', K['C'])
        lines = canvas.lines()
        note_y = 2 + ((len(nodes) + 1) // 2) * 4
    explanation = [t('why.' + key), t('declared')]
    for paragraph in explanation:
        for line in textwrap.wrap(paragraph, max(10, width - 4)):
            if note_y < height:
                lines[note_y] = K['DIM'] + '  ' + line + K['R']
                note_y += 1
    return lines[:height]


def continuity(S):
    brain = cfg(S).get('_brain')
    eid = selected(S).get('id')
    if not brain or not os.path.isdir(brain):
        return [t('no_brain')]
    if not os.path.isfile(os.path.join(A.ROOT, 'session_continuity.py')):
        return [t('no_pilot'), t('capture_explain')]
    import session_continuity as C
    runs = [r for r in C.receipts(brain).get('runs', {}).values()
            if r.get('engine') == eid]
    runs.sort(key=lambda r: r.get('updated') or r.get('captured_at') or '', reverse=True)
    if not runs:
        return [t('no_receipt'), t('capture_explain'), t('checkpoint_explain')]
    r = runs[0]
    state = r.get('capture_state', 'unknown')
    result = [t('last_capture', state=t('capture.' + state)),
              t('date', date=r.get('captured_at') or t('unverified')),
              t('distilled', state=t('yes') if r.get('distilled_at') else t('pending')),
              t('consolidated', state=t('yes') if r.get('consolidated_at') else t('pending')),
              t('capture_explain'), t('checkpoint_explain')]
    return result


def content(S):
    if S.get('connect'):
        C = S['connect']
        state = C.get('connect') or {}
        step = state.get('step', 'intro')
        st = state.get('status') or {}
        rows = [t('wizard.' + step)]
        rows += [('◆ ' if done else '◇ ') + label + ' · ' + t('step.done' if done else 'step.pending')
                 for label, done in setup_steps(S)]
        if step in ('cli', 'cli_confirm'):
            rows += [t('installed') if st.get('cli_present') else t('missing'),
                     t('wizard.cli_actions'), t('wizard.command', cmd=' '.join(st.get('install_cmd', []))),
                     t('wizard.command', cmd=' '.join(st.get('login_cmd', [])))]
        elif step == 'paste':
            rows += ['•' * min(60, len(state.get('buf', ''))), t('wizard.secret')]
        elif step == 'result':
            res = state.get('result') or {}
            rows += [t('wizard.ok') if res.get('ok') and res.get('kind') == 'ok'
                     else t('wizard.auth_error') if res.get('kind') == 'auth'
                     else t('wizard.unverified')]
        else:
            rows += [t('wizard.api'), t('env_names', names=', '.join(st.get('env_vars', []))),
                     st.get('credential_url') or '', t('wizard.secret')]
        return [state.get('provider', '')], rows
    d = selected(S)
    sec = SECTIONS[S['sec']]
    if sec == 'providers':
        rows = providers()
        if not rows:
            return [], [t('empty_providers')]
        p = rows[S['row'] % len(rows)]
        lines = [p['display'], t('connection', value=t('connection.' + p.get('connection', 'unknown'))),
                 t('auth', value=t('auth.' + p.get('auth', 'none'))),
                 t('cost', value=t('cost.' + p.get('cost', 'unknown'))),
                 t('configured') if p.get('present') else t('unverified')]
        if p.get('blocked'):
            lines += [t('blocked')]
        if p.get('env_vars'):
            lines += [t('env_names', names=', '.join(p['env_vars']))]
        if p.get('endpoint'):
            lines += [t('endpoint', value=p['endpoint'])]
        lines += [t('provider.scope'), t('provider_action')]
        return [p['display'] for p in rows], lines
    if sec == 'features':
        rows = _features(d)
        item = rows[S['row'] % len(rows)]
        lines = [item[0], item[1], item[2], t('declared')]
        if S['row'] % len(rows) == 5:
            import json
            brain = cfg(S).get('_brain', '')
            try:
                with open(os.path.join(brain, '.claude', 'settings.local.json'), encoding='utf-8') as fh:
                    settings = json.load(fh)
                configured = bool(settings.get('statusLine'))
            except (OSError, ValueError, TypeError):
                configured = False
            lines += [t('bar_configured') if configured else t('bar_unverified')]
        return [r[0] + ' · ' + r[1] for r in rows], lines
    if sec == 'continuity':
        stages = ('capture', 'checkpoint', 'retrieve', 'distill')
        stage = stages[S['row'] % 4]
        return [t(x) for x in stages], [t(stage), t('flow.' + stage)] + continuity(S)
    _, _, details = status_model(S)
    return [t('binary'), t('login'), t('assignment'), t('guide')], details


def check_login(S, engine=None):
    """Explicit background probe. A registry's ready flag alone is not login proof."""
    if S.get('busy'):
        return
    d = dict(engine or selected(S))
    S['busy'] = True
    S['msg'] = t('checking')
    def worker():
        try:
            import dispatch
            mod = dispatch.load_engine(d['id'])
            st = mod.status() if hasattr(mod, 'status') else {}
            if not d.get('binaries_ok'):
                label = t('missing')
            elif 'session_active' in st:
                label = t('verified') if st['session_active'] else t('needs_login')
            else:
                label = t('unverified')
            S['checks'][d['id']] = {'label': label, 'verified': bool(st.get('session_active')) and bool(d.get('binaries_ok')), 'at': time.time()}
            S['msg'] = label
        except Exception:
            S['msg'] = t('probe_failed')
        finally:
            S['busy'] = False
    threading.Thread(target=worker, daemon=True).start()


def hints():
    return (('Tab', t('hint.engine')), ('◄►', t('hint.section')),
            ('↑↓', t('hint.select')), ('Space', t('hint.detail')),
            ('a', t('hint.agent')), ('Enter', t('hint.connect')),
            ('v', t('hint.verify')), ('u', t('hint.assign')), ('q', t('hint.exit')))


MANAGE_ACTIONS = ('install', 'login', 'verify', 'assign', 'information')


def provider_badge(S, d):
    if not d.get('binaries_ok'):
        return '◇', 'BAD', t('missing')
    if S['checks'].get(d.get('id'), {}).get('verified'):
        return '◆', 'OK', t('verified')
    return '◆', 'OK', t('manager.installed_unknown')


def manager_hints(S):
    return (('↑↓', t('hint.select')), ('Enter', t('manager.open')),
            ('f', t('sec.features')), ('c', t('sec.continuity')),
            ('s', t('sec.status')), ('v', t('hint.verify')), ('q', t('hint.back')))


def render_manager(S, w, h):
    K = A._K()
    catalog = S.get('view') == 'catalog'
    d = selected(S)
    pairs = manager_hints(S)
    if w < 50 or h < 20:
        import responsive_ui
        compact = [engine_name(item) + ' · ' + provider_badge(S,item)[2] for item in S['engines']] if catalog else [engine_name(d)] + [t('manager.' + action) for action in MANAGE_ACTIONS]
        return responsive_ui.hub_frame(compact,w,h,title=t('word'),hint='↑↓ / Enter / f / c / q')
    L = HL.screen_header(K,w,h,t('manager.catalog_sub') if catalog else engine_name(d),
                         word=t('word'),hints=pairs,compact_h=40,refl_min_h=54)
    # Visible destinations retain their actual keyboard shortcuts.
    chips = '   '.join(K['C'] + K['BO'] + '[ ' + key + '  ' + label.upper() + ' ]' + K['R']
                       for key,label in (('Enter',t('manager.open')),('f',t('sec.features')),
                                         ('c',t('sec.continuity')),('s',t('sec.status'))))
    if HL.vis(chips) <= w-1:
        L.append(' '*max(0,(w-1-HL.vis(chips))//2)+chips)
    else:
        L.append(HL.keyline(K,(('Enter',t('manager.open')),('f',t('sec.features')),
                              ('c',t('sec.continuity')),('s',t('sec.status'))),w-1))
    left = []
    if catalog:
        for n,item in enumerate(S['engines']):
            active = n == S['engine']
            left += [(K['C']+K['BO']+'❯ ' if active else K['DIM']+'  ')+engine_name(item)+K['R']]
            installed = bool(item.get('binaries_ok'))
            left += ['    '+(K['OK'] if installed else K['BAD'])+K['BO']+
                     ('◆ ' if installed else '◇ ')+t('installed' if installed else 'missing')+K['R'], '']
        left_title = t('sec.providers')
    else:
        for n,action in enumerate(MANAGE_ACTIONS):
            left += [(K['C']+K['BO']+'❯ ◆ ' if n==S.get('action',0) else K['DIM']+'  ◇ ')+t('manager.'+action)+K['R']]
        left_title = t('manager.actions')
    state = ((S.get('connect') or {}).get('connect') or {})
    installed = bool((state.get('status') or {}).get('cli_present',d.get('binaries_ok')))
    verified = S['checks'].get(d.get('id'),{}).get('verified',False)
    check = S['checks'].get(d.get('id'),{}).get('label',t('unverified'))
    detail = [K['C']+K['BO']+'◆ '+engine_name(d)+K['R'], '',
              (K['OK'] if installed else K['BAD'])+K['BO']+'◆ '+t('installed' if installed else 'missing')+K['R'],
              (K['OK'] if verified else K['B2'])+'◇ '+t('login_state',state=check)+K['R'],'']
    action = MANAGE_ACTIONS[S.get('action',0)] if not catalog else ('login' if installed else 'install')
    detail += [K['C']+K['BO']+t('manager.next')+K['R'],t('manager.help.'+action),'',
               K['B2']+K['BO']+t('manager.information')+K['R'],t('manager.info_visible')]
    if state.get('step') == 'cli_confirm':
        detail += ['',K['C']+K['BO']+t('wizard.cli_confirm')+K['R'],
                   ' '.join((state.get('status') or {}).get('install_cmd',[]))]
    available = h-1-len(L)-3
    map_h = 9 if available>=24 else 0
    panel_h = available-map_h
    side = w>=100
    lw = min(44,(w-5)//3) if side else w-2
    rw = w-lw-4 if side else w-2
    lh = panel_h-2 if side else max(3,panel_h//2-2)
    rh = panel_h-2 if side else max(2,panel_h-lh-4)
    wrapped=[]
    for paragraph in detail:
        wrapped += [HL.clip(paragraph,rw-4)] if '\033' in paragraph else textwrap.wrap(paragraph,max(10,rw-4)) or ['']
    start = max(0, (S['engine']*3 if catalog else S.get('action',0))-lh+3)
    a = HL.full_box(left_title,left[start:start+lh],K,lw,lh,True)
    b = HL.full_box(t('manager.overview'),wrapped,K,rw,rh,False)
    if side:
        L += [' '+HL.pad(x,lw)+'  '+y for x,y in zip(a,b)]
    else:
        L += [' '+x for x in a+b]
    if map_h:
        nodes=((engine_name(d),'c'),(t('installed' if installed else 'missing'),'ok' if installed else 'dk'),
               (t('verified') if verified else t('unverified'),'ok' if verified else 'b2'))
        graph=brain_view.pipeline(HL,K,A._mk,w-6,map_h-2,nodes,('',t('login')),t('manager.map_note'))
        if graph is None:
            graph=[t('manager.map_note')]
        L += [' '+x for x in HL.full_box(t('box.map'),graph,K,w-2,map_h-2,False)]
    L=L[:h-4]+['']*max(0,h-4-len(L))
    legend = K['OK']+'◆ '+t('installed')+K['R']+' · '+K['BAD']+'◇ '+t('missing')+K['R']+' · '+K['B2']+t('unverified')+K['R']
    L += ['', ' '+(S.get('msg') or legend),HL.foot_hints(K,pairs,w)]
    return [HL.clip(line,w-1) for line in L[:h-1]]


def open_information(S, section):
    S['info_return'] = S.get('view','catalog')
    S['guide_state'] = S.pop('connect',None)
    S['view'] = 'info'
    S['sec'] = section
    S['row'] = S['offset'] = 0


def manage_key(S, key):
    pending = ((S.get('connect') or {}).get('connect') or {}).get('step') == 'cli_confirm'
    if pending and key not in ('q','\x1b','\r','\n','\x03'):
        return True
    if key in ('q','\x1b'):
        state = (S.get('connect') or {}).get('connect') or {}
        if state.get('step') == 'cli_confirm':
            state['step'] = 'cli'
        else:
            S.pop('connect',None)
            S['view'] = 'catalog'
        return True
    if key in ('up','down'):
        S['action'] = (S.get('action',0) + (1 if key=='down' else -1)) % len(MANAGE_ACTIONS)
        return True
    if key == 'a' and S['agents']:
        S['agent'] = (S['agent'] + 1) % len(S['agents'])
        return True
    if key not in ('\r','\n','i','l','v','u','f'):
        return None
    state = (S.get('connect') or {}).get('connect') or {}
    if key in ('\r','\n') and state.get('step') == 'cli_confirm':
        return None
    action = MANAGE_ACTIONS[S.get('action',0)] if key in ('\r','\n') else {'i':'install','l':'login','v':'verify','u':'assign','f':'information'}[key]
    if action == 'information':
        open_information(S,1)
        return True
    if action == 'assign':
        agent = cfg(S)
        if agent:
            result = harnesses.set_binding(agent['name'],selected(S)['id'],agent.get('engine',''),actor='motors')
            S['msg'] = t('saved') if result.get('ok') else t('save_failed')
        return True
    if action == 'verify':
        check_login(S)
        return True
    if action == 'install' and (state.get('status') or {}).get('cli_present'):
        S['msg'] = t('installed')
        return True
    if action == 'login' and not (state.get('status') or {}).get('cli_present'):
        S['msg'] = t('manager.install_first')
        S['action'] = 0
        return True
    import config_tui as C
    C._connect_key(S['connect'], 'i' if action == 'install' else 'l')
    if S['connect'].get('shell_request'):
        S['request'] = ('shell',S['connect'].pop('shell_request'))
        return False
    return True


def render(S, w, h):
    if S.get('view') in ('catalog','manage'):
        return render_manager(S,w,h)
    K = A._K()
    w, h = max(1, w), max(2, h)
    rows, detail = content(S) if S['engines'] else ([], [t('empty')])
    if w < 50 or h < 20:
        import responsive_ui
        return responsive_ui.hub_frame(detail, w, h, title=t('word'), hint='q / Esc')
    L = HL.screen_header(K, w, h, t('sub'), word=t('word'), hints=hints(), compact_h=40, refl_min_h=54)
    L.append(A._tab_strip(K, [engine_name(d) for d in S['engines']], S['engine'], w - 1))
    L.append(A._tab_strip(K, [t('sec.' + s) for s in SECTIONS], S['sec'], w - 1))
    c = cfg(S)
    L.append(HL.clip(' ' + t('agent', name=c.get('display') or c.get('name') or '—'), w - 1))
    avail = max(4, h - 1 - len(L) - 3)
    map_h = min(16, max(11, avail // 2)) if avail >= 20 else 0
    box_h = avail - map_h
    side = w >= 100
    lw = min(43, (w - 5) // 3) if side else w - 2
    rw = w - lw - 4 if side else w - 2
    list_h = box_h - 2 if side else max(2, box_h // 3 - 2)
    det_h = box_h - 2 if side else max(1, box_h - list_h - 4)
    index = S['row'] % len(rows) if rows else 0
    start = max(0, index - list_h // 2)
    menu = [(K['C'] + K['BO'] + '❯ ◆ ' if i == index else K['DIM'] + '  ◇ ') + r + K['R']
            for i, r in enumerate(rows)]
    left = HL.full_box(t('box.select'), menu[start:start + list_h], K, lw, list_h, True)
    wrapped = []
    for n, paragraph in enumerate(detail):
        title = n == 0
        if n and ': ' in paragraph:
            label, value = paragraph.split(': ', 1)
            wrapped.append(K['C'] + K['BO'] + '◆ ' + label.upper() + K['R'])
            wrapped += textwrap.wrap(value, max(10, rw - 4)) + ['']
        else:
            for line in textwrap.wrap(paragraph, max(10, rw - 6)):
                wrapped.append(K['C'] + K['BO'] + '◆ ' + line.upper() + K['R'] if title else line)
            wrapped.append('')
    offset = S['offset'] % max(1, len(wrapped))
    right = HL.full_box(t('box.explain'), wrapped[offset:offset + det_h], K, rw, det_h, False)
    if side:
        L += [' ' + HL.pad(a, lw) + '  ' + b for a, b in zip(left, right)]
    else:
        L += [' ' + line for line in left + right]
    if map_h:
        diagram = concept_map(S, K, w - 6, map_h - 2)
        L += [' ' + x for x in HL.full_box(t('box.map'), diagram, K, w - 2, map_h - 2, False)]
    L = L[:h - 4] + [''] * max(0, h - 4 - len(L))
    foot = (('Enter', t('hint.confirm')), ('i', t('hint.install')), ('l', t('hint.login')),
            ('v', t('hint.verify')), ('Esc', t('hint.back'))) if S.get('connect') else hints()
    L += ['', ' ' + (S.get('msg') or t('notice')), HL.foot_hints(K, foot, w)]
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


def act(S, key):
    pending = ((S.get('connect') or {}).get('connect') or {}).get('step') == 'cli_confirm'
    if not pending and S.get('view') in ('catalog','manage') and key in ('f','c','s'):
        open_information(S, {'f':1,'c':2,'s':0}[key])
        return True
    if S.get('view') == 'catalog':
        if key in ('q','\x1b','\x03'):
            return False
        if key == 'v':
            check_login(S)
        elif key in ('up','down','tab') and S['engines']:
            S['engine'] = (S['engine'] + (-1 if key=='up' else 1)) % len(S['engines'])
        elif key in ('\r','\n') and S['engines']:
            name = {'claude-code':'anthropic','codex':'codex','antigravity':'antigravity'}[selected(S)['id']]
            open_provider(S,name)
            S['view'] = 'manage'
            S['action'] = 1 if selected(S).get('binaries_ok') else 0
            S['msg'] = ''
        return True
    if S.get('view') == 'manage':
        handled = manage_key(S,key)
        if handled is not None:
            return handled
    if S.get('view') == 'info' and key in ('q','\x1b'):
        S['view'] = S.pop('info_return','manage')
        if S['view'] == 'catalog':
            S.pop('guide_state',None)
            return True
        S['connect'] = S.pop('guide_state',None)
        provider = ((S.get('connect') or {}).get('connect') or {}).get('provider')
        expected = {'claude-code':'anthropic','codex':'codex','antigravity':'antigravity'}.get(selected(S).get('id'))
        if not S.get('connect') or provider != expected:
            open_provider(S,{'claude-code':'anthropic','codex':'codex','antigravity':'antigravity'}.get(selected(S).get('id'),'codex'))
        return True
    if S.get('connect'):
        import config_tui as C
        if key == '\x03':
            return False
        state = S['connect']
        if key == 'v':
            provider = (state.get('connect') or {}).get('provider')
            eid = {'anthropic': 'claude-code', 'codex': 'codex', 'antigravity': 'antigravity'}.get(provider)
            engine = next((d for d in S['engines'] if d.get('id') == eid), None)
            check_login(S, engine)
            return True
        C._connect_key(state, key)
        if state.get('shell_request'):
            S['request'] = ('shell', state.pop('shell_request'))
            return False
        if state.get('mode') != 'connect':
            S.pop('connect', None)
        return True
    if key in ('q', '\x1b', '\x03'):
        return False
    if not S['engines']:
        return True
    if key == 'tab':
        S['engine'] = (S['engine'] + 1) % len(S['engines'])
        S['row'] = S['offset'] = 0
    elif key in ('left', 'right'):
        S['sec'] = (S['sec'] + (1 if key == 'right' else -1)) % len(SECTIONS)
        S['row'] = S['offset'] = 0
    elif key in ('up', 'down'):
        rows, _ = content(S)
        S['row'] = (S['row'] + (1 if key == 'down' else -1)) % max(1, len(rows))
        S['offset'] = 0
    elif key == ' ':
        S['offset'] += 6
    elif key == 'a' and S['agents']:
        S['agent'] = (S['agent'] + 1) % len(S['agents'])
    elif key == 'v':
        check_login(S)
    elif key in ('\r', '\n'):
        if SECTIONS[S['sec']] == 'providers':
            rows = providers()
            if rows:
                open_provider(S, rows[S['row'] % len(rows)]['name'])
                return True
        else:
            eid = selected(S)['id']
            name = {'claude-code': 'anthropic', 'codex': 'codex'}.get(eid)
            if name:
                open_provider(S, name)
                return True
            if eid == 'antigravity':
                open_antigravity(S)
                return True
            S['request'] = ('guide', eid)
            return False
    elif key == 'u':
        agent = cfg(S)
        if agent:
            result = harnesses.set_binding(agent['name'], selected(S)['id'], agent.get('engine', ''), actor='motors')
            S['msg'] = t('saved') if result.get('ok') else t('save_failed')
    return True


def open_provider(S, name):
    if name == 'antigravity':
        open_antigravity(S)
        return
    import config_tui as C
    state = C.new_state()
    C._open_connect(state, {'provider': name})
    S['connect'] = state
    S['offset'] = 0


def open_antigravity(S):
    import shutil
    # Official installation guide, verified 2026-10-09. No execution on entry.
    command = (['powershell', '-NoProfile', '-Command',
                'irm https://antigravity.google/cli/install.ps1 | iex'] if os.name == 'nt'
               else ['bash', '-c', 'curl -fsSL https://antigravity.google/cli/install.sh | bash'])
    S['connect'] = {'mode': 'connect', 'status': '', 'shell_request': None,
                    'connect': {'provider': 'antigravity', 'step': 'cli',
                                'status': {'cli': 'agy', 'cli_present': bool(shutil.which('agy')),
                                           'install_cmd': command, 'login_cmd': ['agy']},
                                'buf': '', 'result': None}}
    S['offset'] = 0


def run():
    S = initial()
    if not sys.stdin.isatty():
        print('\n'.join(render(S, 110, 44)))
        return
    while True:
        S['request'] = None
        # Existing terminal loop; callbacks stay local, no patched module globals.
        _loop(S)
        request = S.get('request')
        if not request:
            return
        kind, name = request
        if kind == 'shell':
            import config_tui
            import subprocess
            print('\n' + t('wizard.command', cmd=' '.join(name['cmd'])))
            try:
                subprocess.run(name['cmd'], check=False)
            except (OSError, KeyboardInterrupt):
                S['msg'] = t('wizard.error')
            input(t('return'))
            if name.get('provider') == 'antigravity':
                open_antigravity(S)
            else:
                config_tui._reenter_connect_after_shell(S['connect'], name)
        else:
            print('\n' + t('manual_guide') + '\n' + GUIDES.get(name, t('no_guide')))
            input(t('return'))
        S['engines'] = [d for d in harnesses.registry() if d.get('id') in SUPPORTED]


def _loop(S):
    import responsive_ui
    if os.name == 'nt':
        import msvcrt
        out = sys.stdout
        out.write('\033[?1049h\033[?25l')
        try:
            first = True
            while True:
                w, h = A._size(out)
                responsive_ui.paint(out, render(S, w, h), first=first)
                first = False
                if not msvcrt.kbhit():
                    time.sleep(.15)
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
        out = open('/dev/tty', 'w')
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            out.write('\033[?1049h\033[?25l')
            first = True
            while True:
                w, h = A._size(out)
                responsive_ui.paint(out, render(S, w, h), first=first)
                first = False
                if select.select([fd], [], [], .15)[0] and not act(S, _read_key_unix(fd, select)):
                    return
        finally:
            out.write('\033[?25h\033[?1049l')
            out.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            out.close()
            os.close(fd)
