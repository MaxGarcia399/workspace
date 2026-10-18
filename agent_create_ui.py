"""Menús de creación: todas las acciones accesibles con ↑↓ y Enter."""
import skill_source_preferences as prefs
import brain_view

# i18n (lado cliente): el plan + el mapa conceptual los ve el cliente. Import
# guardado con red de seguridad inline (_t) → sin i18n cae al español EXACTO.
# Los textos se resuelven en cada render (funciones, no constantes de módulo)
# para que la pantalla flipee de idioma EN VIVO con el hub.
try:
    import i18n
except Exception:
    i18n = None


def _preset_label(r):
    """Etiqueta VISIBLE de una fuente: las de fábrica (PRESETS) se traducen
    por su posición; un repo propio muestra su label tal cual."""
    if not r.get('custom'):
        for i, (repo, label, _en, _d) in enumerate(prefs.PRESETS):
            if repo == r.get('repo') and r.get('label') == label:
                return _t('addagent.sources.preset.%d.label' % i, label)
    return r.get('label', '')


def _t(key, es):
    if i18n is None:
        return es
    try:
        s = i18n.t(key)
        return s if s != key else es
    except Exception:
        return es


VIEWS = {'plan', 'motor', 'sources', 'repo', 'process', 'cost', 'brain', 'community', 'skill_receipt', 'perms'}


def _onoff(v):
    return 'ON' if v else 'OFF'


def _pref_keys(S):
    """Claves de estado de las dos preguntas: el plan de CREAR y la vista
    previa a CARGAR guardan su respuesta aparte (no se contagian)."""
    if S.get('view') == 'perms':
        return 'perms_brain', 'perms_review'
    return 'brain_free', 'skill_review'


def _pref_rows(S):
    """Los DOS interruptores de permisos y aprendizaje (crear y cargar): leer y
    escribir su cerebro sin preguntar (ON de entrada) y revisión de skills."""
    kf, kr = _pref_keys(S)
    return [('autonomy', _t('addagent.plan.row.brain_free', 'Su cerebro sin preguntar: ') + _onoff(S.get(kf, True))),
            ('review', _t('addagent.plan.row.review', 'Revisión de skills: ') + _onoff(S.get(kr)))]


def _pref_details():
    return {
        'autonomy': [_t('addagent.detail.brain_free.1', 'ON (recomendado): lee, crea y edita dentro de su cerebro sin preguntarte; la terminal, los archivos de fuera y la red te los pregunta.'),
                     _t('addagent.detail.brain_free.2', 'OFF: te pregunta antes de crear o editar cada archivo, también en su cerebro.'),
                     _t('addagent.detail.autonomy.3', 'Enter cambia esta preferencia. Después la cambias cuando quieras en Agentes (Enter sobre el agente).')],
        'review': [_t('addagent.detail.review.1', 'OFF: al cerrar una sesión no corre nada.'),
                   _t('addagent.detail.review.2', 'ON: al abrir la siguiente sesión, tu agente revisa a la vista lo que corregiste en la anterior y mejora sus skills; las skills nuevas se crean directo.'),
                   _t('addagent.detail.review.3', 'Usa un poco de tu suscripción. Enter cambia esta preferencia; después, en Agentes (Enter sobre el agente).')],
    }


def _process():
    return [
        _t('addagent.process.1', '1. Busca SKILL.md en los repositorios que permitiste.'),
        _t('addagent.process.2', '2. Muestra nombre, origen y commit; tú eliges las skills.'),
        _t('addagent.process.3', '3. Obtiene archivos de texto desde GitHub, sin ejecutar nada.'),
        _t('addagent.process.4', '4. Comprueba hashes, rutas, tamaño, secretos e instrucciones sospechosas.'),
        _t('addagent.process.5', '5. Revisa recursos, licencia y requisitos del entorno.'),
        _t('addagent.process.6', '6. Activa el paquete completo si pasa; conserva pendiente lo que requiere revisión.'),
        _t('addagent.process.7', '7. Guarda procedencia, hashes, avisos e índices en el cerebro.'),
        _t('addagent.process.static', 'La revisión es estática: reduce riesgos y no garantiza ausencia de malware.'),
        _t('addagent.process.manual', 'Copiar texto a mano también puede introducir instrucciones maliciosas. Se aplica la misma revisión.'),
        _t('addagent.process.noexec', 'No instala dependencias, no conecta apps y no ejecuta scripts durante la importación.'),
    ]


# Compatibilidad: PROCESS sigue existiendo como snapshot del idioma al importar.
PROCESS = _process()


def rows(S, api):
    v = S['view']
    if 'source_config' not in S:
        S['source_config'] = prefs.load()
    config = S['source_config']
    if v == 'perms':
        return _pref_rows(S) + [('connect', _t('addagent.perms.row.connect', 'CONECTAR')),
                                ('back', _t('addagent.perms.row.back', 'Volver sin conectar'))]
    if v == 'plan':
        return [('motor', _t('addagent.plan.row.motor', 'Motor: ') + (S.get('engine_id') or 'claude-code')),
                ('personalize', _t('addagent.plan.row.personalize', 'Personalización con IA: ') + ('ON' if S.get('personalize') else 'OFF')),
                ('toggle', _t('addagent.plan.row.toggle', 'Obtener skills: ') + ('ON' if S.get('source_skills') else 'OFF')),
                ('skills', _t('addagent.plan.row.skills', 'Elegir skills: %d seleccionadas') % len(S.get('skill_selected', []))),
                ('sources', _t('addagent.plan.row.sources', 'Fuentes permitidas y repos propios'))] + _pref_rows(S) + [
                ('process', _t('addagent.plan.row.process', 'Cómo se revisan las skills')),
                ('cost', _t('addagent.plan.row.cost', 'Consumo y límites de sesión')),
                ('brain', _t('addagent.plan.row.brain', 'Vistas del mapa · sólo información')),
                ('create', _t('addagent.plan.row.create', 'CREAR AGENTE')), ('back', _t('addagent.plan.row.back', 'Volver al formulario'))]
    if v == 'brain':
        return [('route:'+key, label) for key,label in [('setup', _t('addagent.brain.route.setup', 'Composición · carpetas y MD')),('boot', _t('addagent.brain.route.boot', 'Arranque · qué carga')),('save', _t('addagent.brain.route.save', 'Guardar · dónde y cuándo')),('retrieve', _t('addagent.brain.route.retrieve', 'Recuperar · ruta del contexto')),('organize', _t('addagent.brain.route.organize', 'Organizar · al cerrar, sin IA'))]] + [('back', _t('addagent.nav.back_plan', 'Volver al plan'))]
    if v == 'motor':
        return [(d['id'], ('● ' if d['id'] == S.get('engine_id') else '○ ') + d['id'] +
                 (_t('addagent.motor.available', ' · disponible') if d.get('ready') else ' · ' + (d.get('detail') or _t('addagent.motor.unavailable', 'no disponible'))))
                for d in (S.get('harn') or {}).get('list', [])] + [('back', _t('addagent.nav.back_plan', 'Volver al plan'))]
    if v == 'sources':
        result = [('repo:' + str(i), ('[x] ' if r['enabled'] else '[ ] ') + _preset_label(r))
                  for i, r in enumerate(config['repos'])]
        result += [('community', ('[x] ' if config['community'] else '[ ] ') + _t('addagent.sources.community', 'Descubrir comunidad en skills.sh')),
                   ('query', _t('addagent.sources.query', 'Consulta pública: ') + (S.get('community_query') or _t('addagent.sources.unset', 'sin configurar'))),
                   ('add', _t('addagent.sources.add', 'Agregar repositorio de GitHub'))]
        result += [('remove:' + str(i), _t('addagent.sources.remove', 'Quitar repositorio: ') + r['repo'])
                   for i, r in enumerate(config['repos']) if r['custom']]
        return result + [('back', _t('addagent.nav.back_plan', 'Volver al plan'))]
    if v == 'cost':
        agy=[('connect_agy', _t('addagent.cost.connect_agy', 'Conectar lectura de Antigravity'))] if S.get('engine_id')=='antigravity' else []
        return agy + [('refresh_balance', _t('addagent.cost.refresh', 'Actualizar lectura local')), ('back', _t('addagent.nav.back_plan', 'Volver al plan'))]
    if v in ('repo', 'community'):
        return [('input', S.get('repo_input' if v == 'repo' else 'community_input', ''))]
    if v == 'skill_receipt':
        receipt = (S.get('job') or {}).get('skill_sourcing') or {}
        return [('detail:' + str(i), c.get('name', '?') + (_t('addagent.receipt.installed', ' · instalada') if status == 'installed' else _t('addagent.receipt.held', ' · pendiente')))
                for i, (status, c) in enumerate([(k, c) for k in ('installed', 'held') for c in receipt.get(k, [])])] + [('back', _t('addagent.nav.back_result', 'Volver al resultado'))]
    return [('back', _t('addagent.nav.back_plan', 'Volver al plan'))]


def details(S, action, api):
    v = S['view']
    if v == 'process':
        return _process()
    if action in ('autonomy', 'review'):
        return _pref_details()[action]
    if v == 'perms':
        names = ', '.join(n or '?' for n, _c in (S.get('perms_items') or [])[:4])
        if action == 'connect':
            return [_t('addagent.perms.connect.1', 'Conecta: %s') % names,
                    _t('addagent.perms.connect.2', 'Tus respuestas se anotan en su agent.json (viajan con el cerebro) y sus permisos se ajustan a ellas.')]
        return [_t('addagent.perms.back.1', 'Vuelve sin conectar nada.')]
    if v == 'brain':
        route = S.get('brain_route', 'setup')
        return list(brain_view.routes()[route][:3]) + ['', _t('addagent.brain.note.disk', 'DISCO: 0 tokens de modelo · leer contexto y redactar: variables.'), _t('addagent.brain.note.fts5', 'FTS5: índice local derivado; no es una base vectorial.'), _t('addagent.brain.note.capture', 'El agente anota en el momento, con etiqueta; al cerrar, Workspace ordena.'), _t('addagent.brain.note.hooks', 'Si cerraste con la X, el cierre se completa al siguiente arranque.')] + overview_detail(S, api)
    if v == 'cost':
        return cost(S, api)
    if v == 'sources':
        if action.startswith('repo:'):
            r = S['source_config']['repos'][int(action.split(':')[1])]
            return [_t('addagent.sources.repo.label', 'Repositorio: ') + r['repo'], _t('addagent.sources.repo.toggle', 'Enter permite u omite esta fuente.'),
                    _t('addagent.sources.repo.cert', 'Permitir una fuente no certifica sus skills. Cada paquete pasa la misma revisión.'),
                    _t('addagent.sources.repo.public', 'Solo GitHub público; no se descargan ZIP ni instaladores.'),
                    _t('addagent.sources.repo.saved', 'Configuración guardada por usuario.')] + [_t('addagent.sources.preset.%d.desc' % i, description) for i, (repo, label, enabled, description) in enumerate(prefs.PRESETS) if repo == r['repo']]
        if action == 'community':
            return [_t('addagent.sources.comm.dir', 'skills.sh es un directorio de la comunidad.'),
                    _t('addagent.sources.comm.query', 'Al activarlo se enviará únicamente la consulta que configures aquí.'),
                    _t('addagent.sources.comm.origin', 'Cada resultado muestra el repositorio original de GitHub.'),
                    _t('addagent.sources.comm.explicit', 'Las skills de comunidad requieren selección explícita; no se marcan solas.'),
                    _t('addagent.sources.comm.audit', 'Las auditorías externas del directorio no sustituyen la revisión local.')]
        return [_t('addagent.sources.add.hint', 'Agrega owner/repo o https://github.com/owner/repo.'),
                _t('addagent.sources.add.manage', 'Puedes activar, omitir o quitar tus repositorios desde este menú.'),
                _t('addagent.sources.add.free', 'Elegir fuentes no consume tokens de modelo.')]
    if v in ('repo', 'community'):
        return [_t('addagent.input.write', 'Escribe ') + (_t('addagent.input.repo', 'owner/repo o URL del repositorio.') if v == 'repo' else _t('addagent.input.capability', 'una capacidad genérica, por ejemplo: data visualization.')),
                _t('addagent.input.save', 'Enter guarda · Esc vuelve.'), _t('addagent.input.community_note', 'Esta consulta se enviará a skills.sh; evita datos personales.') if v == 'community' else _t('addagent.input.repo_note', 'Solo se aceptan repositorios públicos de github.com.')]
    if v == 'skill_receipt':
        receipt = (S.get('job') or {}).get('skill_sourcing') or {}
        items = [(k, c) for k in ('installed', 'held') for c in receipt.get(k, [])]
        if action.startswith('detail:'):
            status, c = items[int(action.split(':')[1])]
            return [_t('addagent.receipt.origin', 'Origen: ') + c.get('repo', ''), _t('addagent.receipt.commit', 'Commit: ') + c.get('sha', '')[:12]] + c.get('reasons', []) + c.get('compatibility_notes', []) + [_t('addagent.receipt.full', 'Recibo completo: .workspace/skill-sourcing.json')]
        return receipt.get('errors', []) + [_t('addagent.receipt.pick', '↑↓ elige una skill para ver sus resultados.')]
    return {
        'motor': [_t('addagent.detail.motor.1', 'Elige el motor que ejecutará tu agente.'), _t('addagent.detail.motor.2', 'Enter abre la lista de motores y su disponibilidad.')],
        'personalize': [_t('addagent.detail.personalize.1', 'OFF: plantilla local, 0 tokens.'), _t('addagent.detail.personalize.2', 'ON: el modelo redacta identidad, alcance y perfil con tus respuestas.'), _t('addagent.detail.personalize.3', 'Enter cambia esta preferencia.')] + cost(S, api)[:3],
        'toggle': [_t('addagent.detail.toggle.1', 'Encendido, consulta repos de skills en GitHub y skills.sh (si lo permites).'), _t('addagent.detail.toggle.2', '0 tokens de modelo. Solo se activan paquetes que pasan la revisión.'), _t('addagent.detail.toggle.3', 'Enter activa o desactiva.')],
        'skills': [_t('addagent.detail.skills.1', 'Revisa nombre, procedencia, descripción y versión antes de crear.'), _t('addagent.detail.skills.2', 'Enter abre la selección; cada skill se marca con Enter.')],
        'sources': [_t('addagent.detail.sources.1', 'Tú decides qué repositorios se pueden consultar.'), _t('addagent.detail.sources.2', 'Incluye fuentes conocidas, comunidad opcional y tus propios repositorios.')],
        'process': [_t('addagent.detail.process.1', 'Mira cada paso de la descarga y revisión automática.'), _t('addagent.detail.process.2', 'Los archivos con alertas quedan pendientes y no se activan.')],
        'cost': [_t('addagent.detail.cost.1', 'Consulta el costo estimado y las barras de uso disponibles.'), _t('addagent.detail.cost.2', 'Tokens estimados y porcentaje de límite son medidas diferentes.')],
        'brain': [_t('addagent.detail.brain.1', 'Ver archivos y carpetas que tendrá tu agente.')],
        'create': [_t('addagent.detail.create.1', 'Crear con las preferencias visibles en este menú.')] + cost(S, api)[:3],
        'back': [_t('addagent.detail.back.1', 'Vuelve para editar tus respuestas.')],
    }.get(action, [_t('addagent.detail.default', 'Enter selecciona este motor.')])


def cost(S, api):
    estimate = api.agent_create_job.estimate()
    result = [_t('addagent.cost.create', 'Crear: ') + _generation_label(S, api),
              _t('addagent.cost.sourcing_free', 'Obtener y revisar skills: 0 tokens de modelo.'),
              _t('addagent.cost.boot_est', 'Arranque futuro: ~%s tokens estimados.') % api._fmt_ktok(estimate.get('boot_tokens')) if estimate.get('boot_tokens') is not None else _t('addagent.cost.boot_none', 'Arranque futuro: sin estimación disponible.')]
    balance = api._saldo_eval(S)
    if balance:
        for label, free, reset, expired in balance['vent']:
            result.append(_t('addagent.cost.balance', '%s: %s %d%% libre%s') % (label, api._barra_saldo(api._K(), free, 10, api._K()['C']), free, (_t('addagent.cost.resets', ' · reinicia ') + reset) if reset else ''))
        result += [_t('addagent.cost.reading', 'Lectura ') + balance['edad'] + (_t('addagent.cost.stale', ' · antigua: solo referencia') if balance.get('stale') else ''),
                   _t('addagent.cost.limit_note', 'El límite depende del modelo y uso; no se convierte a tokens exactos.')]
    else:
        result += [_t('addagent.cost.no_reading', 'Límite: sin lectura vigente; no se inventa un saldo.'),
                   (_t('addagent.cost.agy_hint', 'Antigravity: abre una sesión y /usage; luego actualiza esta lectura local.') if S.get('engine_id')=='antigravity' else _t('addagent.cost.cc_hint', 'Claude Code: la statusline guarda la lectura cuando la sesión informa límites.'))]
    return result


def panels(S, api, iw, dw, cap):
    menu = rows(S, api)
    cursor = min(S.get('option_cursor', 0), len(menu) - 1)
    S['option_cursor'] = cursor
    start = max(0, min(cursor - cap // 2, len(menu) - cap))
    left = []
    for i in range(start, min(len(menu), start + cap)):
        K = api._K()
        style = K['C'] + K['BO'] if i == cursor else K['GREY']
        left.append(api.HL.clip(style + ((K['PTR'] + ' ') if i == cursor else '  ') + menu[i][1] + K['R'], iw))
    action = menu[cursor][0]
    text = details(S, action, api)
    if S['view'] == 'plan':
        text = cost(S, api)[:1] + text
    right = []
    for line in text:
        right += api._wrap(line, dw)
    offset = min(S.get('detail_scroll', 0), max(0, len(right) - cap))
    S['detail_scroll'] = offset
    return left, right[offset:offset + cap]


def action(S, key, api):
    v = S['view']
    if v not in VIEWS:
        return False
    if v in ('repo', 'community'):
        field = 'repo_input' if v == 'repo' else 'community_input'
        if key in ('\r', '\n'):
            if v == 'repo':
                try:
                    config = prefs.add(S['source_config'], S.get(field, ''))
                    prefs.save(config)
                    S['source_config'] = config
                    S['msg'] = _t('addagent.msg.repo_saved', 'repositorio guardado ✓')
                except (ValueError, OSError) as exc:
                    S['msg'] = str(exc)
                    return True
            if v == 'community':
                S['community_query'] = S.get('community_input', '').strip()
                S['msg'] = _t('addagent.msg.query_saved', 'consulta guardada ✓')
            S['view'], S['option_cursor'] = 'sources', 0
            api._lanza_skills(S, force=True)
        elif key == '\x1b':
            S['view'], S['option_cursor'] = 'sources', 0
        elif key in ('\x7f', '\b', '\x08'):
            S[field] = S.get(field, '')[:-1]
        elif len(key) == 1 and key.isprintable() and len(S.get(field, '')) < (200 if v == 'repo' else 120):
            S[field] = S.get(field, '') + key
        return True
    menu = rows(S, api)
    cursor = min(S.get('option_cursor', 0), len(menu) - 1)
    chosen = menu[cursor][0]
    if v=='plan' and key=='tab':
        S['map_focus']=not S.get('map_focus',False)
        return True
    if v=='plan' and S.get('map_focus'):
        keys=list(brain_view.routes())
        if key in ('left','right','up','down'):
            pos=keys.index(S.get('brain_route','setup'))
            S['brain_route']=keys[(pos+(-1 if key in ('left','up') else 1))%len(keys)]
        elif key in ('\r','\n','\x1b'):
            S['map_focus']=False
        return True
    if key in ('up', 'down', 'tab'):
        S['option_cursor'] = (cursor + (-1 if key == 'up' else 1)) % len(menu)
        S['detail_scroll'] = 0
        return True
    if key in ('right', 'left'):
        S['detail_scroll'] = max(0, S.get('detail_scroll', 0) + (1 if key == 'right' else -1))
        return True
    if key == '\x1b':
        if v == 'perms':
            S['view'] = S.get('perms_origen') or 'menu'
        else:
            S['view'] = 'crear' if v == 'plan' else ('done' if v == 'skill_receipt' else 'plan')
        S['option_cursor'] = 0
        return True
    shortcut = {'p': 'personalize', 's': 'toggle', 'k': 'skills'}
    if v == 'plan' and key.lower() in shortcut:
        chosen = shortcut[key.lower()]
    elif key not in ('\r', '\n', ' '):
        return True
    kf, kr = _pref_keys(S)
    if chosen == 'autonomy':
        S[kf] = not S.get(kf, True)
        return True
    if chosen == 'review':
        S[kr] = not S.get(kr)
        return True
    if v == 'perms':
        if chosen == 'connect':
            api._ljob_start(S, S.get('perms_items') or [], S.get('perms_origen') or 'menu',
                            prefs={'autonomy': (S.get('perms_base') or 'brain') if S.get(kf, True) else 'ask',
                                   'skill_review': bool(S.get(kr))})
        else:
            S['view'] = S.get('perms_origen') or 'menu'
        S['option_cursor'] = 0
        return True
    if v == 'brain':
        if chosen == 'back':
            S['view'] = 'plan'
            S['option_cursor'] = next(i for i, item in enumerate(rows(S, api)) if item[0] == 'brain')
        else:
            S['brain_route'] = chosen.split(':',1)[1]
        return True
    if v == 'plan':
        if chosen == 'brain':
            S['map_focus'] = True
            S['msg'] = _t('addagent.msg.map_nav', '←→ elige vista · Enter vuelve a los ajustes')
            return True
        decision = 'skills' if chosen == 'toggle' else chosen
        if decision in _REVIEW_KEYS:
            explored = S.setdefault('plan_explored', [])
            if decision not in explored:
                explored.append(decision)
        if chosen == 'create':
            if S.get('source_skills') and (S.get('sourcing') or {}).get('state') == 'busy':
                S['msg'] = _t('addagent.msg.searching', 'Buscando skills; espera o desactiva Obtener skills.')
            elif S.get('personalize') and (api._saldo_eval(S) or {}).get('verdict') == 'sin':
                S['msg'] = _t('addagent.msg.limit_exhausted', 'Límite agotado: desactiva personalización o espera al reinicio.')
            else:
                api._crear_ya(S)
        elif chosen == 'personalize':
            available, note = api._perso_disp(S)
            if available:
                S['personalize'] = not S.get('personalize')
            else:
                S['msg'] = _t('addagent.msg.perso_unavailable', 'Personalización no disponible: ') + note
        elif chosen == 'toggle':
            S['source_skills'] = not S.get('source_skills')
            api._lanza_skills(S)
        else:
            S['view'] = 'crear' if chosen == 'back' else chosen
            if chosen == 'skills':
                api._lanza_skills(S)
            S['option_cursor'], S['detail_scroll'] = 0, 0
    elif v == 'motor':
        if chosen == 'back':
            S['view'] = 'plan'
        elif chosen in api._harn_elegibles(S):
            S['engine_id'], S['view'] = chosen, 'plan'
        else:
            S['msg'] = _t('addagent.msg.engine_unavailable', 'Motor no disponible; revisa su estado.')
        S['option_cursor'] = 0
    elif v == 'sources':
        import copy
        config = copy.deepcopy(S['source_config'])
        if chosen.startswith('repo:'):
            r = config['repos'][int(chosen.split(':')[1])]
            r['enabled'] = not r['enabled']
        elif chosen.startswith('remove:'):
            config['repos'].pop(int(chosen.split(':')[1]))
        elif chosen == 'community':
            config['community'] = not config['community']
        elif chosen in ('add', 'query'):
            S['view'] = 'repo' if chosen == 'add' else 'community'
            S['repo_input'] = ''
            S['community_input'] = S.get('community_query', '')
            return True
        else:
            S['view'], S['option_cursor'] = 'plan', 0
            return True
        try:
            prefs.save(config)
            S['source_config'] = config
            S['msg'] = _t('addagent.msg.saved', 'guardado ✓')
            S['option_cursor'] = min(cursor, len(rows(S, api)) - 1)
            api._lanza_skills(S, force=True)
        except (OSError, ValueError) as exc:
            S['msg'] = _t('addagent.msg.save_failed', 'No se guardó la configuración: ') + str(exc)
    elif v == 'cost' and chosen == 'connect_agy':
        import antigravity_usage
        state = antigravity_usage.ensure_statusline()
        S['msg'] = {'ready': _t('addagent.msg.agy_ready', 'Conectado ✓ · abre Antigravity y /usage; luego actualiza la lectura.'), 'custom': _t('addagent.msg.agy_custom', 'Hay una statusline propia; se conserva. Consulta /usage dentro de Antigravity.'), 'blocked': _t('addagent.msg.agy_blocked', 'No se pudo conectar; revisa los permisos de settings.json de Antigravity.')}[state]
    elif v == 'cost' and chosen == 'refresh_balance':
        S['saldo'] = None
        api._lanza_saldo(S)
        S['msg'] = _t('addagent.msg.reading_local', 'Leyendo el último registro local; no consulta al modelo.')
    elif chosen == 'back':
        S['view'], S['option_cursor'] = ('done' if v == 'skill_receipt' else 'plan'), 0
    return True


def _plan_guide():
    return {
    'motor': (_t('addagent.guide.motor.head', 'EL MOTOR DE TU AGENTE'), _t('addagent.guide.motor.lead', 'El lugar donde tu agente piensa y trabaja.'),
              _t('addagent.guide.motor.body', 'El motor ejecuta las tareas y aporta el modelo, las herramientas y su cuota de uso. La identidad, la memoria y las skills permanecen en la carpeta del cerebro. Elegir otro motor cambia la ejecución; los hooks y funciones disponibles dependen de ese runtime.'), _t('addagent.guide.motor.enter', 'Abrir motores')),
    'personalize': (_t('addagent.guide.personalize.head', 'UNA IDENTIDAD A TU MEDIDA'), _t('addagent.guide.personalize.lead', 'Tus respuestas pueden convertirse en su voz y criterio.'),
                    _t('addagent.guide.personalize.body', 'Con ON, el modelo usa tus respuestas para redactar identidad, alcance y perfil del dueño: define su voz, sus tareas y los límites con los que empezará. Con OFF, esos datos se incorporan a la plantilla local sin una llamada al modelo. La estimación de esta redacción aparece bajo el mapa.'), _t('addagent.guide.personalize.enter', 'Cambiar ON / OFF')),
    'autonomy': (_t('addagent.guide.brain_free.head', 'SU CEREBRO, SIN PEDIR PERMISO'), _t('addagent.guide.brain_free.lead', 'Leer y escribir su cerebro es su trabajo principal.'),
                 _t('addagent.guide.brain_free.body', 'Con ON (recomendado), el agente lee, crea y edita archivos dentro de su cerebro sin pedirte permiso; para usar la terminal, tocar archivos fuera de su cerebro o salir a la red te pregunta. Con OFF, te pregunta antes de crear o editar cualquier archivo, también en su cerebro. En ningún caso se desactivan las protecciones del motor.'), _t('addagent.guide.autonomy.enter', 'Cambiar ON / OFF')),
    'review': (_t('addagent.guide.review.head', 'APRENDE DE TUS CORRECCIONES'), _t('addagent.guide.review.lead', 'Opcional: tu agente mejora sus skills al abrir la siguiente sesión.'),
               _t('addagent.guide.review.body', 'Con ON, al cerrar cada sesión Workspace guarda una vista de lo que pasó; al abrir la siguiente, tu agente la revisa a la vista y mejora las skills que usó con lo que corregiste. Las skills nuevas se crean directo. Nada corre sin ventana y usa un poco de tu suscripción en esa sesión. Con OFF no pasa nada.'), _t('addagent.guide.review.enter', 'Cambiar ON / OFF')),
    'toggle': (_t('addagent.guide.toggle.head', 'PROCEDIMIENTOS PARA SUS TAREAS'), _t('addagent.guide.toggle.lead', 'Apagado por defecto. Encendido, consulta repos de skills en GitHub y skills.sh.'),
               _t('addagent.guide.toggle.body', 'Al activar esta opción se obtienen las propuestas seleccionadas desde las fuentes permitidas y se revisan antes de incorporarlas. Buscar y revisar no usa un modelo ni ejecuta código remoto. Los paquetes con alertas quedan pendientes y se muestran por separado; desactivarla conserva las skills base del cerebro.'), _t('addagent.guide.toggle.enter', 'Cambiar ON / OFF')),
    'skills': (_t('addagent.guide.skills.head', 'TÚ ELIGES QUÉ SABRÁ HACER'), _t('addagent.guide.skills.lead', 'Revisa las propuestas antes de incorporarlas.'),
               _t('addagent.guide.skills.body', 'Una skill contiene instrucciones y recursos para una tarea concreta. Aquí revisas su propósito, repositorio y versión y decides cuáles proponer para tu agente. La selección todavía no la instala: al crear se revisa el paquete y sólo se incorporan los que pasan los controles, con un recibo de lo instalado y lo pendiente.'), _t('addagent.guide.skills.enter', 'Abrir selección')),
    'sources': (_t('addagent.guide.sources.head', 'EL ORIGEN TAMBIÉN LO DECIDES TÚ'), _t('addagent.guide.sources.lead', 'Elige de dónde se puede obtener contenido.'),
                _t('addagent.guide.sources.body', 'La búsqueda consulta sólo los repositorios permitidos. Puedes activar u omitir las fuentes conocidas y agregar repositorios públicos de GitHub. El directorio de comunidad es opcional y sus resultados requieren selección explícita. Permitir una fuente amplía dónde se busca; cada paquete mantiene la misma revisión local.'), _t('addagent.guide.sources.enter', 'Abrir fuentes')),
    'process': (_t('addagent.guide.process.head', 'DE LA FUENTE A TU CEREBRO'), _t('addagent.guide.process.lead', 'Sigue el recorrido de cada paquete.'),
                _t('addagent.guide.process.body', 'Se obtienen archivos del commit elegido, se verifican hashes, rutas, textos, recursos, licencia y dependencias. La revisión es estática; no ejecuta código remoto.'), _t('addagent.guide.process.enter', 'Ver proceso completo')),
    'cost': (_t('addagent.guide.cost.head', 'CONSUMO A LA VISTA'), _t('addagent.guide.cost.lead', 'Comprueba el costo antes de crear.'),
             _t('addagent.guide.cost.body', 'La plantilla y la revisión local no consumen tokens de modelo. La personalización sí. Los porcentajes de cuota se muestran desde lecturas locales con su antigüedad.'), _t('addagent.guide.cost.enter', 'Abrir consumo')),
    'brain': (_t('addagent.guide.brain.head', 'EL AGENTE QUE ESTÁS CONSTRUYENDO'), _t('addagent.guide.brain.lead', 'Explora todas tus respuestas y preferencias.'),
              _t('addagent.guide.brain.body', 'El panorama inferior se actualiza con tus cambios. Aquí puedes leer el detalle completo, incluidos textos largos, fuentes omitidas y configuración del dueño.'), _t('addagent.guide.brain.enter', 'Elegir vista del mapa')),
    'create': (_t('addagent.guide.create.head', 'DALE VIDA A TU AGENTE'), _t('addagent.guide.create.lead', 'Crea con la configuración que estás viendo.'),
               _t('addagent.guide.create.body', 'Se prepara el cerebro, se conecta el motor y se revisan las skills elegidas. Verás el avance y los motivos de cualquier pendiente.'), _t('addagent.guide.create.enter', 'Crear agente')),
    'back': (_t('addagent.guide.back.head', 'AFINA TUS RESPUESTAS'), _t('addagent.guide.back.lead', 'Puedes volver al formulario y seguir construyendo.'),
             _t('addagent.guide.back.body', 'Tus respuestas permanecen. Cambiar las tareas puede renovar las propuestas de skills; revisa la selección antes de crear.'), _t('addagent.guide.back.enter', 'Editar formulario')),
    }


def _plan_explanations():
    return {'motor': _t('addagent.impact.motor', 'Al crear se registra el motor elegido y se prepara su conexión con el cerebro. Para usarlo '
          'necesitas que esté instalado y que su sesión tenga acceso al proveedor. La disponibilidad que '
          'muestra el menú ayuda a elegir, pero no sustituye la autenticación ni garantiza que todas las '
          'herramientas se comporten igual entre motores.\n'
          '\n'
          'La cuota corresponde al motor con el que generarás o trabajarás, no a la carpeta del agente. '
          'Cambiar esta elección permite conservar el contenido del cerebro mientras eliges otra forma de '
          'ejecutarlo; consulta el costo antes de activar la personalización.'),
 'personalize': _t('addagent.impact.personalize', 'La redacción parte del rol, propósito, tono, estilo, alcance, límites y datos del dueño que '
                'escribiste. El objetivo es convertir esas respuestas en instrucciones coherentes para el '
                'arranque, no entrenar un modelo nuevo. Una respuesta específica produce un punto de partida '
                'más útil que una descripción ambigua.\n'
                '\n'
                'El resultado se guarda como archivos editables del cerebro. Podrás ajustar su voz o sus '
                'límites después de crearlo. La personalización consume tokens de una llamada al modelo; la '
                'cifra es una estimación y no incluye todas las conversaciones futuras del agente.'),
 'autonomy': _t('addagent.impact.brain_free', 'Queda en su agent.json y viaja con el cerebro; cada motor lo traduce a sus propios permisos. Lo que pide permiso depende del motor: Claude Code te pregunta; Codex, Antigravity y los demás te preguntan o lo bloquean cuando no pueden preguntar. Guardar memoria (`workspace memoria`) nunca pide permiso.\n\nLo cambias cuando quieras en Agentes (Enter sobre el agente).'),
 'review': _t('addagent.impact.review', 'La revisión la hace el propio agente al abrir su siguiente sesión, a la vista, con lo que pasó en la anterior; solo toca skills/ de su cerebro y las skills nuevas se crean directo. Las sesiones muy cortas no se revisan y, como mucho, se pide una vez cada dos horas por cerebro.\n\nQueda anotado en su agent.json ("skill_review"). Si un agente no dice nada, manda el ajuste global hooks.skill_review, que viene apagado.'),
 'toggle': _t('addagent.impact.toggle', 'Las skills amplían los procedimientos que el agente puede consultar para resolver tareas. '
           'Obtenerlas no equivale a ejecutarlas durante la creación ni a cargar todo su contenido en cada '
           'conversación: el catálogo permite localizar las relevantes cuando hacen falta.\n'
           '\n'
           'Si la revisión detecta un problema, esa propuesta queda pendiente y el resultado explica el '
           'motivo. Por eso el número de propuestas del mapa es una intención de importación, no una promesa '
           'de cuántas quedarán instaladas.'),
 'skills': _t('addagent.impact.skills', 'Conviene elegir por las tareas que esperas delegar: investigar, analizar datos, preparar '
           'documentos u otro trabajo concreto. Más skills no garantizan mejores respuestas; también añaden '
           'instrucciones y recursos que revisar y mantener. El catálogo organiza las disponibles para '
           'consultar la adecuada bajo demanda.\n'
           '\n'
           'El repositorio y la versión permiten saber de dónde vino cada paquete. La revisión puede dejar '
           'una selección pendiente; el recibo final distingue lo instalado de lo que necesita atención. '
           'Usar una skill en una sesión puede consumir tokens al leer sus instrucciones y trabajar con '
           'ellas, aunque obtenerla no use un modelo.'),
 'sources': _t('addagent.impact.sources', 'Agregar un repositorio autoriza consultarlo como fuente de propuestas, no ejecutar su contenido '
            'ni aprobar automáticamente todas sus skills. Los resultados conservan su procedencia y versión '
            'para que puedas rastrear lo que entra al cerebro. Omitir una fuente limita la búsqueda a las '
            'restantes.\n'
            '\n'
            'Si activas la consulta pública de comunidad, se envía al directorio la consulta que configures. '
            'Usa una capacidad genérica y evita datos personales en esa consulta. Los resultados apuntan a '
            'su repositorio de origen y pasan la revisión local antes de incorporarse.'),
 'process': _t('addagent.impact.process', 'El proceso descarga los archivos del paquete desde la versión elegida y comprueba su integridad '
            'y estructura. Revisa rutas, enlaces, instrucciones, recursos incluidos, licencia y dependencias '
            'para detectar contenido que no se deba activar automáticamente. No lanza instaladores ni '
            'ejecuta scripts del repositorio como parte de esta revisión.\n'
            '\n'
            'Es una revisión estática: detecta señales y aplica reglas, pero no demuestra que un paquete sea '
            'seguro en todos los usos. Las alertas se conservan como motivos concretos y dejan la skill '
            'pendiente. El recibo registra origen, versión y resultado para que puedas revisar qué se '
            'incorporó y por qué.'),
 'cost': _t('addagent.impact.cost', 'El costo de creación corresponde a la generación con IA cuando la activas. Copiar la plantilla, '
         'consultar fuentes y revisar archivos localmente no consume tokens de modelo. Una vez creado, cada '
         'conversación puede gastar tokens al cargar contexto, leer instrucciones y producir respuestas; '
         'esos usos futuros quedan fuera de la cifra de creación.\n'
         '\n'
         'Las barras muestran porcentaje de cuota libre según la última lectura disponible del motor. Ese '
         'porcentaje no equivale a un número exacto de tokens ni permite asegurar cuántas conversaciones '
         'quedan. Si la lectura es antigua o desconocida, actualízala en esta sección; las fechas de '
         'reinicio y los detalles del proveedor ayudan a interpretar el saldo.'),
 'brain': _t('addagent.impact.brain', 'Las vistas del mapa son informativas: cambiar de Composición a Arranque, Guardar, Recuperar u '
          'Organizar resalta un recorrido sin modificar tus preferencias. Los fragmentos junto a los '
          'archivos muestran cómo se traducen tus respuestas al formato del cerebro. Las propuestas de '
          'skills siguen sujetas a revisión.\n'
          '\n'
          'Explorar estos recorridos ayuda a distinguir lo que se carga al iniciar de lo que se consulta '
          'después, cómo guarda el agente y cómo ordena Workspace la memoria al cerrar. La carpeta es el contenido '
          'persistente; el motor es quien lo lee y trabaja con él. Los costos de contexto y redacción '
          'dependen de cuánto contenido se use en cada acción.'),
 'create': _t('addagent.impact.create', 'Se valida el nombre y destino, se prepara la carpeta desde la plantilla y se registra la '
           'identidad del agente. Después se conecta su runtime y se realizan los pasos de personalización e '
           'importación que hayas activado. La pantalla de avance muestra qué está ocurriendo y el resultado '
           'resume lo completado.\n'
           '\n'
           'Las propuestas con alertas se informan por separado para que una selección no se confunda con '
           'una instalación. Revisa ese resultado antes de usar el agente. Esta acción crea el setup; las '
           'vistas anteriores sólo lo representan. El costo indicado corresponde a la generación '
           'configurada, no al uso posterior.'),
 'back': _t('addagent.impact.back', 'Volver te permite afinar el rol, propósito, límites, tareas y perfil del dueño conservando las '
         'respuestas de esta creación. Cambiar esos datos cambia lo que se sembrará en los archivos y lo que '
         'se usará para redactar la identidad si activas IA.\n'
         '\n'
         'Si modificas las tareas o las skills solicitadas, revisa las propuestas y su selección antes de '
         'crear: las capacidades que antes tenían sentido pueden dejar de corresponder al nuevo objetivo. '
         'Aún estás configurando el agente; regresar al formulario no crea el cerebro.')}


def _route_explanations():
    return {'setup': _t('addagent.route.setup.impact', 'El formulario aporta el rol, la voz, los límites y el perfil del dueño. La plantilla aporta el '
          'orden de lectura, la estructura de memoria y el catálogo de procedimientos. BOOT define cómo '
          'empieza el agente; STATE conserva memoria y sesiones; wiki guarda conocimiento enlazado y skills '
          'los procedimientos.\n'
          '\n'
          'El mapa representa el punto de partida, no una carpeta ya creada. Los fragmentos de tus '
          'respuestas permiten ver qué parte del cerebro estás definiendo. Las skills propuestas sólo se '
          'incorporan si pasa su revisión; las que queden pendientes se identifican en el resultado.'),
 'boot': _t('addagent.route.boot.impact', 'El agente comienza en BRAIN.md (su archivo de identidad; CLAUDE.md, AGENTS.md y GEMINI.md solo apuntan a él para cada motor) y sigue su orden de lectura: identidad y reglas en BOOT, después '
         'memoria curada, índice y perfil del socio. Al abrir una pestaña, Workspace le entrega además su '
         'memoria: el resumen, lo vigente, las notas nuevas y la maleta del motor anterior, igual en '
         'cualquier motor.\n'
         '\n'
         'La wiki y las instrucciones completas de las skills se consultan cuando la tarea las necesita, '
         'evitando leer todo el cerebro de entrada. Cargar estos documentos sí ocupa contexto del modelo; el '
         'costo depende de su longitud y del runtime. El contenido en disco permanece aunque cambies de '
         'sesión.'),
 'save': _t('addagent.route.save.impact', 'Mientras trabaja, el agente guarda cada cosa en el momento con `workspace memoria nota` y una '
         'etiqueta: decisión, pendiente, hecho, nota, dato o preferencia. Cada pendiente recibe un id (P-3) '
         'para cerrarlo después, y el resumen de la pestaña se guarda con `workspace memoria checkpoint`. El '
         'agente nunca edita la ficha a mano.\n'
         '\n'
         'Al cerrar, en cualquier motor, Workspace arma sin IA la maleta: lo último que pediste, la última '
         'respuesta y los archivos que tocó, para que el siguiente motor siga donde quedó. Si cerraste con la '
         'X, el cierre se completa al siguiente arranque. Escribir y ordenar archivos no usa tokens de modelo; '
         'las notas del agente ocupan un poco de su respuesta.'),
 'retrieve': _t('addagent.route.retrieve.impact', 'Para recuperar contexto se empieza por el índice de STATE y se abre el archivo señalado. Si '
             'falta una ruta útil, la búsqueda local FTS5 puede localizar coincidencias y, como alternativa, '
             'se busca texto con grep. En la wiki se parte de index.md y se siguen los enlaces hacia las '
             'notas relacionadas.\n'
             '\n'
             'El agente lee el detalle necesario para la pregunta, no todas las notas por defecto. La '
             'búsqueda local no usa tokens de modelo; los resultados que se incorporan al contexto y la '
             'respuesta sí. Este recorrido usa índices, archivos y enlaces: FTS5 es búsqueda textual local, '
             'no una base de embeddings.'),
 'organize': _t('addagent.route.organize.impact', 'Al cerrar cada sesión, Workspace ordena la memoria con código, sin IA: rehace la lista de lo vigente (pendientes abiertos y decisiones), sube los datos y preferencias a STATE/MEMORY.md para todas las pestañas y, cuando la ficha crece, deja lo vigente y las notas recientes y mueve las viejas, completas, a archivo/. MEMORY.md pasa sus entradas más viejas a memoria-archivo/ al superar 200 líneas.\n\nNada se borra, nada espera tu revisión y ninguna IA corre sin ventana. Mover o indexar archivos localmente no usa tokens de modelo.')}


_BASE_SKILLS = None


def overview_sections(S, api):
    """Datos de la selección actual; ninguna propuesta se presenta instalada."""
    global _BASE_SKILLS
    from pathlib import Path
    values = S.get('vals') or {}
    def value(key):
        return str(values.get(key) or api.FIELDS[key][1] or _t('addagent.ov.undefined', 'sin definir')).strip()
    config = S.get('source_config') or prefs.defaults()
    chosen = [c for c in (S.get('sourcing') or {}).get('candidates', [])
              if c['source_url'] in S.get('skill_selected', set())] if S.get('source_skills') else []
    if _BASE_SKILLS is None:
        _BASE_SKILLS = sum(1 for _ in Path(api.agent_admin.BRAIN_TEMPLATE).glob('skills/*/*/SKILL.md'))
    base_map = api._mapa_cerebro()
    structure = ['%s%s' % (label, (_t('addagent.ov.base_files', ' · %d archivos base') % count) if count is not None else '') for label, count, desc in base_map]
    sections = [
        (_t('addagent.ov.sec.identity', 'IDENTIDAD · TU FORMULARIO'), [(_t('addagent.ov.f.name', 'Nombre'), value('nombre')),
             (_t('addagent.ov.f.visible', 'Visible'), values.get('visible') or value('nombre').capitalize()),
             (_t('addagent.ov.f.role', 'Rol'), value('rol')), (_t('addagent.ov.f.purpose', 'Propósito'), value('proposito')), (_t('addagent.ov.f.tone', 'Tono'), value('tono')),
             (_t('addagent.ov.f.style', 'Estilo'), value('estilo')), (_t('addagent.ov.f.lang', 'Idioma'), value('idioma'))]),
        (_t('addagent.ov.sec.scope', 'ALCANCE · MEMORIA · DUEÑO'), [(_t('addagent.ov.f.does', 'Hace'), value('alcance')), (_t('addagent.ov.f.limits', 'Límites'), value('limites')),
             (_t('addagent.ov.f.tasks', 'Tareas'), value('ejemplos')), (_t('addagent.ov.f.owner', 'Dueño'), value('dueño')), (_t('addagent.ov.f.who', 'Quién es'), value('dueño_quien')),
             (_t('addagent.ov.f.how', 'Cómo trabaja'), value('dueño_como')), (_t('addagent.ov.f.needs', 'Qué necesita'), value('dueño_necesita'))]),
        (_t('addagent.ov.sec.skills', 'SKILLS · ORIGEN · REVISIÓN'), [(_t('addagent.ov.f.requested', 'Solicitadas'), value('skills')),
             (_t('addagent.ov.f.base', 'Base'), _t('addagent.ov.base_count', '%d skills incluidas en la plantilla') % _BASE_SKILLS),
             (_t('addagent.ov.f.import', 'Importación'), _t('addagent.ov.import_pending', '%d propuestas · revisión pendiente') % len(chosen) if S.get('source_skills') else _t('addagent.ov.disabled', 'desactivada')),
             (_t('addagent.ov.f.search', 'Búsqueda'), _t('addagent.ov.search_busy', 'en curso') if (S.get('sourcing') or {}).get('state') == 'busy' else _t('addagent.ov.search_done', 'terminada') if (S.get('sourcing') or {}).get('state') == 'done' else _t('addagent.ov.search_none', 'sin iniciar'))]
             + [(_t('addagent.ov.f.proposal', 'Propuesta'), '%s · %s @ %s' % (c['name'], c['repo'], c['sha'][:8])) for c in chosen]
             + [(_t('addagent.ov.f.allowed', 'Fuentes permitidas'), ', '.join(r['repo'] for r in config['repos'] if r['enabled']) or _t('addagent.ov.none', 'ninguna')),
                (_t('addagent.ov.f.skipped', 'Fuentes omitidas'), ', '.join(r['repo'] for r in config['repos'] if not r['enabled']) or _t('addagent.ov.none', 'ninguna')),
                (_t('addagent.ov.f.community', 'Comunidad'), _t('addagent.ov.comm_on', 'ON · selección explícita') if config['community'] else 'OFF'),
                (_t('addagent.ov.f.pubquery', 'Consulta pública'), S.get('community_query') or _t('addagent.sources.unset', 'sin configurar')),
                (_t('addagent.ov.f.review', 'Revisión'), _t('addagent.ov.review_val', 'estática · hashes, rutas, textos, recursos y licencia'))]),
        (_t('addagent.ov.sec.setup', 'SETUP · ESTRUCTURA DEL CEREBRO'), [(_t('addagent.ov.f.engine', 'Motor'), S.get('engine_id') or 'claude-code'),
             (_t('addagent.ov.f.identity', 'Identidad'), _t('addagent.ov.identity_ai', 'redacción con IA') if S.get('personalize') else _t('addagent.ov.identity_tpl', 'plantilla local')),
             (_t('addagent.ov.f.perms', 'Permisos'), _t('addagent.ov.perms_brain', 'libre en su cerebro; lo demás te lo pregunta') if S.get('brain_free', True) else _t('addagent.ov.perms_ask', 'te pregunta antes de escribir, también en su cerebro')),
             (_t('addagent.ov.f.skillreview', 'Revisión de skills'), _onoff(S.get('skill_review'))),
             (_t('addagent.ov.f.dest', 'Destino'), api._ruta_corta(api.agent_admin.default_brain_dest(values.get('nombre') or 'agente')))]
             + [(_t('addagent.ov.f.structure', 'Estructura'), line) for line in structure]
             + [(_t('addagent.ov.f.atcreate', 'Al crear'), _t('addagent.ov.atcreate_val', 'identidad portable + registro + tema + hooks/statusline + launcher')),
                (_t('addagent.ov.f.consumption', 'Consumo'), api.HL.strip_ansi(cost(S, api)[0]) if hasattr(api.HL, 'strip_ansi') else cost(S, api)[0]),
                (_t('addagent.ov.f.receipt', 'Recibo de skills'), '.workspace/skill-sourcing.json')]
             + [(_t('addagent.ov.f.costquota', 'Costo y cuota'), line) for line in cost(S, api)[1:]]),
    ]
    return sections, chosen, _BASE_SKILLS


def overview_detail(S, api):
    sections, chosen, base = overview_sections(S, api)
    result = [_t('addagent.ov.preview', 'VISTA PREVIA · todavía no se ha creado el agente.')]
    for title, fields in sections:
        result += [title]
        result += ['%s: %s' % pair for pair in fields]
    result += [_t('addagent.ov.not_installed', 'Las skills propuestas todavía no están instaladas. Las alertas quedan pendientes.')]
    return result


class _MapCanvas:
    """Lienzo de celdas: colores del tema y ancho Unicode real."""
    def __init__(self, api, K, width, height):
        self.api, self.K, self.width, self.height = api, K, width, height
        self.cells = [[[' ', K['DK']] for _ in range(width)] for _ in range(height)]

    def put(self, x, y, value, color=None, limit=None):
        if not 0 <= y < self.height:
            return
        plain = ' '.join(str(value).split())
        text = self.api.HL.clip(plain, limit if limit is not None else max(0, self.width - x))
        for char in text:
            size = self.api.HL.vis(char)
            if size == 0:
                if 0 < x <= self.width:
                    self.cells[y][x-1][0] += char
                continue
            if 0 <= x and x + size <= self.width:
                self.cells[y][x] = [char, color or self.K['WH']]
                for continuation in range(1, size):
                    self.cells[y][x+continuation] = ['', color or self.K['WH']]
            x += size

    def edge(self, x1, y1, x2, y2, active=True):
        color = self.K['B2'] if active else self.K['DK']
        if y1 == y2:
            for x in range(min(x1,x2), max(x1,x2)+1):
                self.put(x,y1,'─' if active else '┄',color)
        elif x1 == x2:
            for y in range(min(y1,y2), max(y1,y2)+1):
                self.put(x1,y,'│' if active else '┆',color)

    def lines(self):
        output=[]
        for cells in self.cells:
            text='';previous=None
            for char,color in cells:
                if color != previous:
                    text += self.K['R'] + color
                    previous=color
                text += char
            output.append(text + self.K['R'])
        return output


def _generation_label(S, api):
    if not S.get('personalize'):
        return _t('addagent.gen.tpl', '0 tokens · plantilla local')
    estimate = api.agent_create_job.estimate().get('personalize_tokens')
    return _t('addagent.gen.ai_est', '~%s tokens estimados · IA ON') % api._fmt_ktok(estimate) if estimate is not None else _t('addagent.gen.ai_noest', 'IA ON · sin estimación disponible')


def quota_lines(S, api, K, width):
    """Comparación visible de medidas distintas, sin inventar tokens disponibles."""
    generation = _t('addagent.quota.generate', 'GENERAR AGENTE  ·  ') + _generation_label(S, api).replace(_t('addagent.gen.sfx_ai', ' · IA ON'), '').replace(_t('addagent.gen.sfx_tpl', ' · plantilla local'), '')
    prefix = ' ' * max(0,(width-api.HL.vis(generation))//2) if width >= 108 else ''
    result = [K['C'] + K['BO'] + prefix + generation + K['R']]
    balance = api._saldo_eval(S)
    if balance:
        pieces=[]
        for label, free, reset, expired in balance['vent']:
            pieces.append(_t('addagent.quota.free', '%s %s %d%% libre%s') % (label, api._barra_saldo(K,free,12,K['OK'] if free else K['BAD']),free, ''))
        if len(pieces) == 2:
            if width >= 100:
                result.append(K['DIM'] + _t('addagent.quota.plan', 'PLAN  ') + K['R'] + pieces[0] + '   │   ' + pieces[1])
            else:
                result.append(_t('addagent.quota.plan', 'PLAN  ') + ' · '.join(_t('addagent.quota.free_short', '%s %d%% libre') % (label,free) for label,free,reset,expired in balance['vent']))
        else:
            result.extend(pieces[:4])
        if balance.get('stale'):
            result[-1] += K['DIM']+_t('addagent.quota.old', ' · dato antiguo')+K['R']
    else:
        result += [K['DIM']+_t('addagent.quota.unknown', 'Cuota disponible: desconocida')+K['R']]
    return [(' ' * max(0,(width-api.HL.vis(line))//2) if width >= 108 and i else '') + api.HL.clip(line,width) for i,line in enumerate(result)]


def overview_panel(S, api, K, width, height):
    """Reusable literal folder graph; quota keeps a reserved visible area."""
    sections, chosen, base = overview_sections(S, api)
    inner, capacity = width - 4, height - 2
    quota = quota_lines(S, api, K, inner)
    model = brain_view.projection(S.get('vals') or {}, base, len(chosen), bool(S.get('personalize')))
    route = S.get('brain_route', 'setup')
    graph_h = max(0, capacity - len(quota))
    if graph_h >= 4:
        model['engine'] = S.get('engine_id') or 'claude-code'
        estimate = api.agent_create_job.estimate().get('boot_tokens')
        model['boot_cost'] = _t('addagent.ov.boot_est', '~%s tokens estimados (plantilla)') % api._fmt_ktok(estimate) if estimate is not None else _t('addagent.ov.boot_none', 'sin estimación de arranque')
        config = S.get('source_config') or prefs.defaults()
        model['sources'] = [r['repo'] for r in config['repos'] if r['enabled']]
        model['sourcing_on'] = bool(S.get('source_skills'))
        model['community'] = bool(config['community'])
        model['origins'] = [c['name']+' @ '+c['sha'][:8] for c in chosen]
        tabs=[]
        for key,label in [('setup', _t('addagent.tab.setup', 'Composición')),('boot', _t('addagent.tab.boot', 'Arranque')),('save', _t('addagent.tab.save', 'Guardar')),('retrieve', _t('addagent.tab.retrieve', 'Recuperar')),('organize', _t('addagent.tab.organize', 'Organizar'))]:
            col=K[brain_view.routes()[key][3]] if key==route else K['DIM']
            tabs.append(col+(K['BO'] if key==route else '')+('› ' if key==route and S.get('map_focus') else '')+'[ '+label+' ]'+K['R'])
        strip='  '.join(tabs)
        strip=' '*max(0,(inner-api.HL.vis(strip))//2)+strip
        body=[strip]+brain_view.render(model, api, K, _MapCanvas, inner, max(0,graph_h-1), route)
    else:
        body = [K['C']+'◇ '+model['name']+_t('addagent.ov.fallback_skills', ' · Obtener skills: ')+('ON' if S.get('source_skills') else 'OFF')+_t('addagent.ov.fallback_counts', ' · %d base + %d propuestas') % (base,len(chosen))+K['R']][:max(1,graph_h)]
        if graph_h > 1:
            body += [_t('addagent.ov.fallback2', 'skills/ · %d base + %d propuestas') % (base,len(chosen))]
    body += quota

    return api.HL.full_box(_t('addagent.ov.box_title', 'TU CEREBRO EN CONSTRUCCIÓN'),body,K,width,capacity,border=K['B2'],label=K['B']+K['BO'])


_REVIEW_KEYS=('motor','personalize','skills','sources','process','cost')


def onboarding(S):
    visited=set(S.get('plan_explored', [])) & set(_REVIEW_KEYS)
    return len(visited),len(_REVIEW_KEYS)-len(visited)




