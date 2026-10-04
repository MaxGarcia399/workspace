"""Menús de creación: todas las acciones accesibles con ↑↓ y Enter."""
import skill_source_preferences as prefs
import brain_view

VIEWS = {'plan', 'motor', 'sources', 'repo', 'process', 'cost', 'brain', 'community', 'skill_receipt'}
PROCESS = [
    '1. Busca SKILL.md en los repositorios que permitiste.',
    '2. Muestra nombre, origen y commit; tú eliges las skills.',
    '3. Obtiene archivos de texto desde GitHub, sin ejecutar nada.',
    '4. Comprueba hashes, rutas, tamaño, secretos e instrucciones sospechosas.',
    '5. Revisa recursos, licencia y requisitos del entorno.',
    '6. Activa el paquete completo si pasa; conserva pendiente lo que requiere revisión.',
    '7. Guarda procedencia, hashes, avisos e índices en el cerebro.',
    'La revisión es estática: reduce riesgos y no garantiza ausencia de malware.',
    'Copiar texto a mano también puede introducir instrucciones maliciosas. Se aplica la misma revisión.',
    'No instala dependencias, no conecta apps y no ejecuta scripts durante la importación.',
]


def rows(S, api):
    v = S['view']
    if 'source_config' not in S:
        S['source_config'] = prefs.load()
    config = S['source_config']
    if v == 'plan':
        return [('motor', 'Motor: ' + (S.get('engine_id') or 'claude-code')),
                ('personalize', 'Personalización con IA: ' + ('ON' if S.get('personalize') else 'OFF')),
                ('toggle', 'Obtener skills: ' + ('ON' if S.get('source_skills') else 'OFF')),
                ('skills', 'Elegir skills: %d seleccionadas' % len(S.get('skill_selected', []))),
                ('sources', 'Fuentes permitidas y repos propios'),
                ('process', 'Cómo se revisan las skills'),
                ('cost', 'Consumo y límites de sesión'),
                ('brain', 'Vistas del mapa · sólo información'),
                ('create', 'CREAR AGENTE'), ('back', 'Volver al formulario')]
    if v == 'brain':
        return [('route:'+key, label) for key,label in [('setup','Composición · carpetas y MD'),('boot','Arranque · qué carga'),('save','Guardar · dónde y cuándo'),('retrieve','Recuperar · ruta del contexto'),('organize','Organizar · consolidación')]] + [('back','Volver al plan')]
    if v == 'motor':
        return [(d['id'], ('● ' if d['id'] == S.get('engine_id') else '○ ') + d['id'] +
                 (' · disponible' if d.get('ready') else ' · ' + (d.get('detail') or 'no disponible')))
                for d in (S.get('harn') or {}).get('list', [])] + [('back', 'Volver al plan')]
    if v == 'sources':
        result = [('repo:' + str(i), ('[x] ' if r['enabled'] else '[ ] ') + r['label'])
                  for i, r in enumerate(config['repos'])]
        result += [('community', ('[x] ' if config['community'] else '[ ] ') + 'Descubrir comunidad en skills.sh'),
                   ('query', 'Consulta pública: ' + (S.get('community_query') or 'sin configurar')),
                   ('add', 'Agregar repositorio de GitHub')]
        result += [('remove:' + str(i), 'Quitar repositorio: ' + r['repo'])
                   for i, r in enumerate(config['repos']) if r['custom']]
        return result + [('back', 'Volver al plan')]
    if v == 'cost':
        agy=[('connect_agy','Conectar lectura de Antigravity')] if S.get('engine_id')=='antigravity' else []
        return agy + [('refresh_balance', 'Actualizar lectura local'), ('back', 'Volver al plan')]
    if v in ('repo', 'community'):
        return [('input', S.get('repo_input' if v == 'repo' else 'community_input', ''))]
    if v == 'skill_receipt':
        receipt = (S.get('job') or {}).get('skill_sourcing') or {}
        return [('detail:' + str(i), c.get('name', '?') + (' · instalada' if status == 'installed' else ' · pendiente'))
                for i, (status, c) in enumerate([(k, c) for k in ('installed', 'held') for c in receipt.get(k, [])])] + [('back', 'Volver al resultado')]
    return [('back', 'Volver al plan')]


def details(S, action, api):
    v = S['view']
    if v == 'process':
        return PROCESS
    if v == 'brain':
        route = S.get('brain_route', 'setup')
        return list(brain_view.ROUTES[route][:3]) + ['', 'DISCO: 0 tokens de modelo · leer contexto y redactar: variables.', 'FTS5: índice local derivado; no es una base vectorial.', 'Al cerrar trabajo significativo: captura del agente, no un temporizador.', 'Hooks de respaldo: según motor/configuración; cierre abrupto puede omitirlos.'] + overview_detail(S, api)
    if v == 'cost':
        return cost(S, api)
    if v == 'sources':
        if action.startswith('repo:'):
            r = S['source_config']['repos'][int(action.split(':')[1])]
            return ['Repositorio: ' + r['repo'], 'Enter permite u omite esta fuente.',
                    'Permitir una fuente no certifica sus skills. Cada paquete pasa la misma revisión.',
                    'Solo GitHub público; no se descargan ZIP ni instaladores.',
                    'Configuración guardada por usuario.'] + [description for repo, label, enabled, description in prefs.PRESETS if repo == r['repo']]
        if action == 'community':
            return ['skills.sh es un directorio de la comunidad.',
                    'Al activarlo se enviará únicamente la consulta que configures aquí.',
                    'Cada resultado muestra el repositorio original de GitHub.',
                    'Las skills de comunidad requieren selección explícita; no se marcan solas.',
                    'Las auditorías externas del directorio no sustituyen la revisión local.']
        return ['Agrega owner/repo o https://github.com/owner/repo.',
                'Puedes activar, omitir o quitar tus repositorios desde este menú.',
                'Elegir fuentes no consume tokens de modelo.']
    if v in ('repo', 'community'):
        return ['Escribe ' + ('owner/repo o URL del repositorio.' if v == 'repo' else 'una capacidad genérica, por ejemplo: data visualization.'),
                'Enter guarda · Esc vuelve.', 'Esta consulta se enviará a skills.sh; evita datos personales.' if v == 'community' else 'Solo se aceptan repositorios públicos de github.com.']
    if v == 'skill_receipt':
        receipt = (S.get('job') or {}).get('skill_sourcing') or {}
        items = [(k, c) for k in ('installed', 'held') for c in receipt.get(k, [])]
        if action.startswith('detail:'):
            status, c = items[int(action.split(':')[1])]
            return ['Origen: ' + c.get('repo', ''), 'Commit: ' + c.get('sha', '')[:12]] + c.get('reasons', []) + c.get('compatibility_notes', []) + ['Recibo completo: .workspace/skill-sourcing.json']
        return receipt.get('errors', []) + ['↑↓ elige una skill para ver sus resultados.']
    return {
        'motor': ['Elige el motor que ejecutará tu agente.', 'Enter abre la lista de motores y su disponibilidad.'],
        'personalize': ['OFF: plantilla local, 0 tokens.', 'ON: el modelo redacta identidad, alcance y perfil con tus respuestas.', 'Enter cambia esta preferencia.'] + cost(S, api)[:3],
        'toggle': ['Obtiene procedimientos reutilizables para las tareas que describiste.', '0 tokens de modelo. Solo se activan paquetes que pasan la revisión.', 'Enter activa o desactiva.'],
        'skills': ['Revisa nombre, procedencia, descripción y versión antes de crear.', 'Enter abre la selección; cada skill se marca con Enter.'],
        'sources': ['Tú decides qué repositorios se pueden consultar.', 'Incluye fuentes conocidas, comunidad opcional y tus propios repositorios.'],
        'process': ['Mira cada paso de la descarga y revisión automática.', 'Los archivos con alertas quedan pendientes y no se activan.'],
        'cost': ['Consulta el costo estimado y las barras de uso disponibles.', 'Tokens estimados y porcentaje de límite son medidas diferentes.'],
        'brain': ['Ver archivos y carpetas que tendrá tu agente.'],
        'create': ['Crear con las preferencias visibles en este menú.'] + cost(S, api)[:3],
        'back': ['Vuelve para editar tus respuestas.'],
    }.get(action, ['Enter selecciona este motor.'])


def cost(S, api):
    estimate = api.agent_create_job.estimate()
    result = ['Crear: ' + _generation_label(S, api),
              'Obtener y revisar skills: 0 tokens de modelo.',
              'Arranque futuro: ~%s tokens estimados.' % api._fmt_ktok(estimate.get('boot_tokens')) if estimate.get('boot_tokens') is not None else 'Arranque futuro: sin estimación disponible.']
    balance = api._saldo_eval(S)
    if balance:
        for label, free, reset, expired in balance['vent']:
            result.append('%s: %s %d%% libre%s' % (label, api._barra_saldo(api._K(), free, 10, api._K()['C']), free, (' · reinicia ' + reset) if reset else ''))
        result += ['Lectura ' + balance['edad'] + (' · antigua: solo referencia' if balance.get('stale') else ''),
                   'El límite depende del modelo y uso; no se convierte a tokens exactos.']
    else:
        result += ['Límite: sin lectura vigente; no se inventa un saldo.',
                   ('Antigravity: abre una sesión y /usage; luego actualiza esta lectura local.' if S.get('engine_id')=='antigravity' else 'Claude Code: la statusline guarda la lectura cuando la sesión informa límites.')]
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
        left.append(api.HL.clip(style + ('› ' if i == cursor else '  ') + menu[i][1] + K['R'], iw))
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
                    S['msg'] = 'repositorio guardado ✓'
                except (ValueError, OSError) as exc:
                    S['msg'] = str(exc)
                    return True
            if v == 'community':
                S['community_query'] = S.get('community_input', '').strip()
                S['msg'] = 'consulta guardada ✓'
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
        keys=list(brain_view.ROUTES)
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
        S['view'] = 'crear' if v == 'plan' else ('done' if v == 'skill_receipt' else 'plan')
        S['option_cursor'] = 0
        return True
    shortcut = {'p': 'personalize', 's': 'toggle', 'k': 'skills'}
    if v == 'plan' and key.lower() in shortcut:
        chosen = shortcut[key.lower()]
    elif key not in ('\r', '\n', ' '):
        return True
    if v == 'brain':
        if chosen == 'back':
            S['view'], S['option_cursor'] = 'plan', 7
        else:
            S['brain_route'] = chosen.split(':',1)[1]
        return True
    if v == 'plan':
        if chosen == 'brain':
            S['map_focus'] = True
            S['msg'] = '←→ elige vista · Enter vuelve a los ajustes'
            return True
        decision = 'skills' if chosen == 'toggle' else chosen
        if decision in _REVIEW_KEYS:
            explored = S.setdefault('plan_explored', [])
            if decision not in explored:
                explored.append(decision)
        if chosen == 'create':
            if S.get('source_skills') and (S.get('sourcing') or {}).get('state') == 'busy':
                S['msg'] = 'Buscando skills; espera o desactiva Obtener skills.'
            elif S.get('personalize') and (api._saldo_eval(S) or {}).get('verdict') == 'sin':
                S['msg'] = 'Límite agotado: desactiva personalización o espera al reinicio.'
            else:
                api._crear_ya(S)
        elif chosen == 'personalize':
            available, note = api._perso_disp(S)
            if available:
                S['personalize'] = not S.get('personalize')
            else:
                S['msg'] = 'Personalización no disponible: ' + note
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
            S['msg'] = 'Motor no disponible; revisa su estado.'
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
            S['msg'] = 'guardado ✓'
            S['option_cursor'] = min(cursor, len(rows(S, api)) - 1)
            api._lanza_skills(S, force=True)
        except (OSError, ValueError) as exc:
            S['msg'] = 'No se guardó la configuración: ' + str(exc)
    elif v == 'cost' and chosen == 'connect_agy':
        import antigravity_usage
        state = antigravity_usage.ensure_statusline()
        S['msg'] = {'ready':'Conectado ✓ · abre Antigravity y /usage; luego actualiza la lectura.', 'custom':'Hay una statusline propia; se conserva. Consulta /usage dentro de Antigravity.', 'blocked':'No se pudo conectar; revisa los permisos de settings.json de Antigravity.'}[state]
    elif v == 'cost' and chosen == 'refresh_balance':
        S['saldo'] = None
        api._lanza_saldo(S)
        S['msg'] = 'Leyendo el último registro local; no consulta al modelo.'
    elif chosen == 'back':
        S['view'], S['option_cursor'] = ('done' if v == 'skill_receipt' else 'plan'), 0
    return True


_PLAN_GUIDE = {
    'motor': ('EL MOTOR DE TU AGENTE', 'El lugar donde tu agente piensa y trabaja.',
              'El motor ejecuta las tareas y aporta el modelo, las herramientas y su cuota de uso. La identidad, la memoria y las skills permanecen en la carpeta del cerebro. Elegir otro motor cambia la ejecución; los hooks y funciones disponibles dependen de ese runtime.', 'Abrir motores'),
    'personalize': ('UNA IDENTIDAD A TU MEDIDA', 'Tus respuestas pueden convertirse en su voz y criterio.',
                    'Con ON, el modelo usa tus respuestas para redactar identidad, alcance y perfil del dueño: define su voz, sus tareas y los límites con los que empezará. Con OFF, esos datos se incorporan a la plantilla local sin una llamada al modelo. La estimación de esta redacción aparece bajo el mapa.', 'Cambiar ON / OFF'),
    'toggle': ('PROCEDIMIENTOS PARA SUS TAREAS', 'Decide si quieres incorporar skills al crear.',
               'Al activar esta opción se obtienen las propuestas seleccionadas desde las fuentes permitidas y se revisan antes de incorporarlas. Buscar y revisar no usa un modelo ni ejecuta código remoto. Los paquetes con alertas quedan pendientes y se muestran por separado; desactivarla conserva las skills base del cerebro.', 'Cambiar ON / OFF'),
    'skills': ('TÚ ELIGES QUÉ SABRÁ HACER', 'Revisa las propuestas antes de incorporarlas.',
               'Una skill contiene instrucciones y recursos para una tarea concreta. Aquí revisas su propósito, repositorio y versión y decides cuáles proponer para tu agente. La selección todavía no la instala: al crear se revisa el paquete y sólo se incorporan los que pasan los controles, con un recibo de lo instalado y lo pendiente.', 'Abrir selección'),
    'sources': ('EL ORIGEN TAMBIÉN LO DECIDES TÚ', 'Elige de dónde se puede obtener contenido.',
                'La búsqueda consulta sólo los repositorios permitidos. Puedes activar u omitir las fuentes conocidas y agregar repositorios públicos de GitHub. El directorio de comunidad es opcional y sus resultados requieren selección explícita. Permitir una fuente amplía dónde se busca; cada paquete mantiene la misma revisión local.', 'Abrir fuentes'),
    'process': ('DE LA FUENTE A TU CEREBRO', 'Sigue el recorrido de cada paquete.',
                'Se obtienen archivos del commit elegido, se verifican hashes, rutas, textos, recursos, licencia y dependencias. La revisión es estática; no ejecuta código remoto.', 'Ver proceso completo'),
    'cost': ('CONSUMO A LA VISTA', 'Comprueba el costo antes de crear.',
             'La plantilla y la revisión local no consumen tokens de modelo. La personalización sí. Los porcentajes de cuota se muestran desde lecturas locales con su antigüedad.', 'Abrir consumo'),
    'brain': ('EL AGENTE QUE ESTÁS CONSTRUYENDO', 'Explora todas tus respuestas y preferencias.',
              'El panorama inferior se actualiza con tus cambios. Aquí puedes leer el detalle completo, incluidos textos largos, fuentes omitidas y configuración del dueño.', 'Elegir vista del mapa'),
    'create': ('DALE VIDA A TU AGENTE', 'Crea con la configuración que estás viendo.',
               'Se prepara el cerebro, se conecta el motor y se revisan las skills elegidas. Verás el avance y los motivos de cualquier pendiente.', 'Crear agente'),
    'back': ('AFINA TUS RESPUESTAS', 'Puedes volver al formulario y seguir construyendo.',
             'Tus respuestas permanecen. Cambiar las tareas puede renovar las propuestas de skills; revisa la selección antes de crear.', 'Editar formulario'),
}

_PLAN_EXPLANATIONS = {'motor': 'Al crear se registra el motor elegido y se prepara su conexión con el cerebro. Para usarlo '
          'necesitas que esté instalado y que su sesión tenga acceso al proveedor. La disponibilidad que '
          'muestra el menú ayuda a elegir, pero no sustituye la autenticación ni garantiza que todas las '
          'herramientas se comporten igual entre motores.\n'
          '\n'
          'La cuota corresponde al motor con el que generarás o trabajarás, no a la carpeta del agente. '
          'Cambiar esta elección permite conservar el contenido del cerebro mientras eliges otra forma de '
          'ejecutarlo; consulta el costo antes de activar la personalización.',
 'personalize': 'La redacción parte del rol, propósito, tono, estilo, alcance, límites y datos del dueño que '
                'escribiste. El objetivo es convertir esas respuestas en instrucciones coherentes para el '
                'arranque, no entrenar un modelo nuevo. Una respuesta específica produce un punto de partida '
                'más útil que una descripción ambigua.\n'
                '\n'
                'El resultado se guarda como archivos editables del cerebro. Podrás ajustar su voz o sus '
                'límites después de crearlo. La personalización consume tokens de una llamada al modelo; la '
                'cifra es una estimación y no incluye todas las conversaciones futuras del agente.',
 'toggle': 'Las skills amplían los procedimientos que el agente puede consultar para resolver tareas. '
           'Obtenerlas no equivale a ejecutarlas durante la creación ni a cargar todo su contenido en cada '
           'conversación: el catálogo permite localizar las relevantes cuando hacen falta.\n'
           '\n'
           'Si la revisión detecta un problema, esa propuesta queda pendiente y el resultado explica el '
           'motivo. Por eso el número de propuestas del mapa es una intención de importación, no una promesa '
           'de cuántas quedarán instaladas.',
 'skills': 'Conviene elegir por las tareas que esperas delegar: investigar, analizar datos, preparar '
           'documentos u otro trabajo concreto. Más skills no garantizan mejores respuestas; también añaden '
           'instrucciones y recursos que revisar y mantener. El catálogo organiza las disponibles para '
           'consultar la adecuada bajo demanda.\n'
           '\n'
           'El repositorio y la versión permiten saber de dónde vino cada paquete. La revisión puede dejar '
           'una selección pendiente; el recibo final distingue lo instalado de lo que necesita atención. '
           'Usar una skill en una sesión puede consumir tokens al leer sus instrucciones y trabajar con '
           'ellas, aunque obtenerla no use un modelo.',
 'sources': 'Agregar un repositorio autoriza consultarlo como fuente de propuestas, no ejecutar su contenido '
            'ni aprobar automáticamente todas sus skills. Los resultados conservan su procedencia y versión '
            'para que puedas rastrear lo que entra al cerebro. Omitir una fuente limita la búsqueda a las '
            'restantes.\n'
            '\n'
            'Si activas la consulta pública de comunidad, se envía al directorio la consulta que configures. '
            'Usa una capacidad genérica y evita datos personales en esa consulta. Los resultados apuntan a '
            'su repositorio de origen y pasan la revisión local antes de incorporarse.',
 'process': 'El proceso descarga los archivos del paquete desde la versión elegida y comprueba su integridad '
            'y estructura. Revisa rutas, enlaces, instrucciones, recursos incluidos, licencia y dependencias '
            'para detectar contenido que no se deba activar automáticamente. No lanza instaladores ni '
            'ejecuta scripts del repositorio como parte de esta revisión.\n'
            '\n'
            'Es una revisión estática: detecta señales y aplica reglas, pero no demuestra que un paquete sea '
            'seguro en todos los usos. Las alertas se conservan como motivos concretos y dejan la skill '
            'pendiente. El recibo registra origen, versión y resultado para que puedas revisar qué se '
            'incorporó y por qué.',
 'cost': 'El costo de creación corresponde a la generación con IA cuando la activas. Copiar la plantilla, '
         'consultar fuentes y revisar archivos localmente no consume tokens de modelo. Una vez creado, cada '
         'conversación puede gastar tokens al cargar contexto, leer instrucciones y producir respuestas; '
         'esos usos futuros quedan fuera de la cifra de creación.\n'
         '\n'
         'Las barras muestran porcentaje de cuota libre según la última lectura disponible del motor. Ese '
         'porcentaje no equivale a un número exacto de tokens ni permite asegurar cuántas conversaciones '
         'quedan. Si la lectura es antigua o desconocida, actualízala en esta sección; las fechas de '
         'reinicio y los detalles del proveedor ayudan a interpretar el saldo.',
 'brain': 'Las vistas del mapa son informativas: cambiar de Composición a Arranque, Guardar, Recuperar u '
          'Organizar resalta un recorrido sin modificar tus preferencias. Los fragmentos junto a los '
          'archivos muestran cómo se traducen tus respuestas al formato del cerebro. Las propuestas de '
          'skills siguen sujetas a revisión.\n'
          '\n'
          'Explorar estos recorridos ayuda a distinguir lo que se carga al iniciar de lo que se consulta '
          'después, dónde se capturan sesiones y cómo se consolida la memoria. La carpeta es el contenido '
          'persistente; el motor es quien lo lee y trabaja con él. Los costos de contexto y redacción '
          'dependen de cuánto contenido se use en cada acción.',
 'create': 'Se valida el nombre y destino, se prepara la carpeta desde la plantilla y se registra la '
           'identidad del agente. Después se conecta su runtime y se realizan los pasos de personalización e '
           'importación que hayas activado. La pantalla de avance muestra qué está ocurriendo y el resultado '
           'resume lo completado.\n'
           '\n'
           'Las propuestas con alertas se informan por separado para que una selección no se confunda con '
           'una instalación. Revisa ese resultado antes de usar el agente. Esta acción crea el setup; las '
           'vistas anteriores sólo lo representan. El costo indicado corresponde a la generación '
           'configurada, no al uso posterior.',
 'back': 'Volver te permite afinar el rol, propósito, límites, tareas y perfil del dueño conservando las '
         'respuestas de esta creación. Cambiar esos datos cambia lo que se sembrará en los archivos y lo que '
         'se usará para redactar la identidad si activas IA.\n'
         '\n'
         'Si modificas las tareas o las skills solicitadas, revisa las propuestas y su selección antes de '
         'crear: las capacidades que antes tenían sentido pueden dejar de corresponder al nuevo objetivo. '
         'Aún estás configurando el agente; regresar al formulario no crea el cerebro.'}
_ROUTE_EXPLANATIONS = {'setup': 'El formulario aporta el rol, la voz, los límites y el perfil del dueño. La plantilla aporta el '
          'orden de lectura, la estructura de memoria y el catálogo de procedimientos. BOOT define cómo '
          'empieza el agente; STATE conserva memoria y sesiones; wiki guarda conocimiento enlazado y skills '
          'los procedimientos.\n'
          '\n'
          'El mapa representa el punto de partida, no una carpeta ya creada. Los fragmentos de tus '
          'respuestas permiten ver qué parte del cerebro estás definiendo. Las skills propuestas sólo se '
          'incorporan si pasa su revisión; las que queden pendientes se identifican en el resultado.',
 'boot': 'El agente comienza en CLAUDE.md y sigue su orden de lectura: identidad y reglas en BOOT, después '
         'memoria curada, índice y perfil del socio. Esta capa le permite saber quién es, con quién trabaja '
         'y dónde buscar el resto de la información.\n'
         '\n'
         'La wiki y las instrucciones completas de las skills se consultan cuando la tarea las necesita, '
         'evitando leer todo el cerebro de entrada. Cargar estos documentos sí ocupa contexto del modelo; el '
         'costo depende de su longitud y del runtime. El contenido en disco permanece aunque cambies de '
         'sesión.',
 'save': 'Al terminar trabajo significativo, el agente captura lo ocurrido en la memoria de la pestaña y '
         'añade al inbox lo que debe consolidarse. La sesión conserva el hilo de ese trabajo; el inbox '
         'separa las capturas de la memoria curada para que no todo se convierta en una regla permanente.\n'
         '\n'
         'No hay un temporizador universal de guardado. En Claude, los hooks configurados pueden respaldar '
         'el transcript al compactar y dejar un rastro al cerrar si faltó captura; depende del motor y un '
         'cierre abrupto puede omitirlos. Escribir o copiar archivos localmente no usa tokens de modelo; '
         'redactar un resumen sí puede consumirlos.',
 'retrieve': 'Para recuperar contexto se empieza por el índice de STATE y se abre el archivo señalado. Si '
             'falta una ruta útil, la búsqueda local FTS5 puede localizar coincidencias y, como alternativa, '
             'se busca texto con grep. En la wiki se parte de index.md y se siguen los enlaces hacia las '
             'notas relacionadas.\n'
             '\n'
             'El agente lee el detalle necesario para la pregunta, no todas las notas por defecto. La '
             'búsqueda local no usa tokens de modelo; los resultados que se incorporan al contexto y la '
             'respuesta sí. Este recorrido usa índices, archivos y enlaces: FTS5 es búsqueda textual local, '
             'no una base de embeddings.',
 'organize': 'Las capturas de sesiones e inbox se revisan y consolidan para mantener MEMORY útil y '
             'actualizar INDEX con las rutas correspondientes. Esto separa el registro de lo que pasó de la '
             'información que conviene recordar y recuperar en el futuro.\n'
             '\n'
             'Dream puede proponer candidatos en DESTILADO; su promoción a MEMORY requiere revisión humana. '
             'No se promete un intervalo automático universal. Mover o indexar archivos localmente no usa '
             'tokens de modelo; interpretar, resumir y redactar una consolidación puede consumirlos según el '
             'contenido.'}

_BASE_SKILLS = None


def overview_sections(S, api):
    """Datos de la selección actual; ninguna propuesta se presenta instalada."""
    global _BASE_SKILLS
    from pathlib import Path
    values = S.get('vals') or {}
    def value(key):
        return str(values.get(key) or api.FIELDS[key][1] or 'sin definir').strip()
    config = S.get('source_config') or prefs.defaults()
    chosen = [c for c in (S.get('sourcing') or {}).get('candidates', [])
              if c['source_url'] in S.get('skill_selected', set())] if S.get('source_skills') else []
    if _BASE_SKILLS is None:
        _BASE_SKILLS = sum(1 for _ in Path(api.agent_admin.BRAIN_TEMPLATE).glob('skills/*/*/SKILL.md'))
    base_map = api._mapa_cerebro()
    structure = ['%s%s' % (label, (' · %d archivos base' % count) if count is not None else '') for label, count, desc in base_map]
    sections = [
        ('IDENTIDAD · TU FORMULARIO', [('Nombre', value('nombre')),
             ('Visible', values.get('visible') or value('nombre').capitalize()),
             ('Rol', value('rol')), ('Propósito', value('proposito')), ('Tono', value('tono')),
             ('Estilo', value('estilo')), ('Idioma', value('idioma'))]),
        ('ALCANCE · MEMORIA · DUEÑO', [('Hace', value('alcance')), ('Límites', value('limites')),
             ('Tareas', value('ejemplos')), ('Dueño', value('dueño')), ('Quién es', value('dueño_quien')),
             ('Cómo trabaja', value('dueño_como')), ('Qué necesita', value('dueño_necesita'))]),
        ('SKILLS · ORIGEN · REVISIÓN', [('Solicitadas', value('skills')),
             ('Base', '%d skills incluidas en la plantilla' % _BASE_SKILLS),
             ('Importación', '%d propuestas · revisión pendiente' % len(chosen) if S.get('source_skills') else 'desactivada'),
             ('Búsqueda', 'en curso' if (S.get('sourcing') or {}).get('state') == 'busy' else 'terminada' if (S.get('sourcing') or {}).get('state') == 'done' else 'sin iniciar')]
             + [('Propuesta', '%s · %s @ %s' % (c['name'], c['repo'], c['sha'][:8])) for c in chosen]
             + [('Fuentes permitidas', ', '.join(r['repo'] for r in config['repos'] if r['enabled']) or 'ninguna'),
                ('Fuentes omitidas', ', '.join(r['repo'] for r in config['repos'] if not r['enabled']) or 'ninguna'),
                ('Comunidad', 'ON · selección explícita' if config['community'] else 'OFF'),
                ('Consulta pública', S.get('community_query') or 'sin configurar'),
                ('Revisión', 'estática · hashes, rutas, textos, recursos y licencia')]),
        ('SETUP · ESTRUCTURA DEL CEREBRO', [('Motor', S.get('engine_id') or 'claude-code'),
             ('Identidad', 'redacción con IA' if S.get('personalize') else 'plantilla local'),
             ('Destino', api._ruta_corta(api.agent_admin.default_brain_dest(values.get('nombre') or 'agente')))]
             + [('Estructura', line) for line in structure]
             + [('Al crear', 'identidad portable + registro + tema + hooks/statusline + launcher'),
                ('Consumo', api.HL.strip_ansi(cost(S, api)[0]) if hasattr(api.HL, 'strip_ansi') else cost(S, api)[0]),
                ('Recibo de skills', '.workspace/skill-sourcing.json')]
             + [('Costo y cuota', line) for line in cost(S, api)[1:]]),
    ]
    return sections, chosen, _BASE_SKILLS


def overview_detail(S, api):
    sections, chosen, base = overview_sections(S, api)
    result = ['VISTA PREVIA · todavía no se ha creado el agente.']
    for title, fields in sections:
        result += [title]
        result += ['%s: %s' % pair for pair in fields]
    result += ['Las skills propuestas todavía no están instaladas. Las alertas quedan pendientes.']
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
        return '0 tokens · plantilla local'
    estimate = api.agent_create_job.estimate().get('personalize_tokens')
    return '~%s tokens estimados · IA ON' % api._fmt_ktok(estimate) if estimate is not None else 'IA ON · sin estimación disponible'


def quota_lines(S, api, K, width):
    """Comparación visible de medidas distintas, sin inventar tokens disponibles."""
    generation = 'GENERAR AGENTE  ·  ' + _generation_label(S, api).replace(' · IA ON', '').replace(' · plantilla local', '')
    prefix = ' ' * max(0,(width-api.HL.vis(generation))//2) if width >= 108 else ''
    result = [K['C'] + K['BO'] + prefix + generation + K['R']]
    balance = api._saldo_eval(S)
    if balance:
        pieces=[]
        for label, free, reset, expired in balance['vent']:
            pieces.append('%s %s %d%% libre%s' % (label, api._barra_saldo(K,free,12,K['OK'] if free else K['BAD']),free, ''))
        if len(pieces) == 2:
            if width >= 100:
                result.append(K['DIM'] + 'PLAN  ' + K['R'] + pieces[0] + '   │   ' + pieces[1])
            else:
                result.append('PLAN  ' + ' · '.join('%s %d%% libre' % (label,free) for label,free,reset,expired in balance['vent']))
        else:
            result.extend(pieces[:4])
        if balance.get('stale'):
            result[-1] += K['DIM']+' · dato antiguo'+K['R']
    else:
        result += [K['DIM']+'Cuota disponible: desconocida'+K['R']]
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
        model['boot_cost'] = '~%s tokens estimados (plantilla)' % api._fmt_ktok(estimate) if estimate is not None else 'sin estimación de arranque'
        config = S.get('source_config') or prefs.defaults()
        model['sources'] = [r['repo'] for r in config['repos'] if r['enabled']]
        model['sourcing_on'] = bool(S.get('source_skills'))
        model['community'] = bool(config['community'])
        model['origins'] = [c['name']+' @ '+c['sha'][:8] for c in chosen]
        tabs=[]
        for key,label in [('setup','Composición'),('boot','Arranque'),('save','Guardar'),('retrieve','Recuperar'),('organize','Organizar')]:
            col=K[brain_view.ROUTES[key][3]] if key==route else K['DIM']
            tabs.append(col+(K['BO'] if key==route else '')+('› ' if key==route and S.get('map_focus') else '')+'[ '+label+' ]'+K['R'])
        strip='  '.join(tabs)
        strip=' '*max(0,(inner-api.HL.vis(strip))//2)+strip
        body=[strip]+brain_view.render(model, api, K, _MapCanvas, inner, max(0,graph_h-1), route)
    else:
        body = [K['C']+'◇ '+model['name']+' · Obtener skills: '+('ON' if S.get('source_skills') else 'OFF')+' · %d base + %d propuestas' % (base,len(chosen))+K['R']][:max(1,graph_h)]
        if graph_h > 1:
            body += ['skills/ · %d base + %d propuestas' % (base,len(chosen))]
    body += quota

    return api.HL.full_box('TU CEREBRO EN CONSTRUCCIÓN',body,K,width,capacity,border=K['B2'],label=K['B']+K['BO'])


_REVIEW_KEYS=('motor','personalize','skills','sources','process','cost')


def onboarding(S):
    visited=set(S.get('plan_explored', [])) & set(_REVIEW_KEYS)
    return len(visited),len(_REVIEW_KEYS)-len(visited)


def choice_visual(S, action, api):
    """Mini-diagrama de la decisión y efecto directo en el cerebro."""
    if action == 'motor':
        return ['[ '+(S.get('engine_id') or 'claude-code')+' ] → EJECUCIÓN DEL CEREBRO']
    if action == 'personalize':
        return ['[ '+('IA ON · modelo' if S.get('personalize') else 'IA OFF · plantilla')+' ] → BOOT/ · VOZ + IDENTIDAD',
                'GENERACIÓN: '+_generation_label(S,api)]
    if action in ('skills','toggle','sources','process'):
        selected=len(S.get('skill_selected', [])) if S.get('source_skills') else 0
        return ['[ FUENTES ] → [ OBTENER ] → [ REVISAR ] → skills/',
                '%d propuestas · %s' % (selected,'sin instalar' if S.get('source_skills') else 'importación OFF')]
    if action == 'cost':
        return ['[ GENERACIÓN ] ↔ [ CUOTA DEL PLAN ]', 'Tokens estimados y % de cuota son medidas distintas.']
    if action == 'brain':
        return ['FORMULARIO → BOOT/ + STATE/ + SCOPE', 'FUENTES → REVISIÓN → skills/ → CEREBRO PORTABLE']
    if action == 'create':
        return ['[ CONFIGURACIÓN ] → [ CREAR + REVISAR ] → [ RESULTADO ]']
    return ['[ FORMULARIO ] → [ CONFIGURACIÓN ACTUAL ]']


def plan_screen(S, api, K, w, avail):
    width = w - 2
    stacked = width < 84
    # Reservar el panorama incluso en terminal pequeña; el menú se desplaza.
    bottom = max(17, min(36, avail - 23)) if avail >= 28 else 6
    top = avail - bottom - 1
    if stacked:
        top = max(8, top)
        bottom = max(6, avail - top - 1)
    menu = rows(S, api)
    cursor = min(S.get('option_cursor', 0), len(menu) - 1)
    S['option_cursor'] = cursor
    roomy = top >= 22 and not stacked
    if stacked:
        left_h = max(4, top * 55 // 100)
        right_h = top - left_h
        lw = rw = width
        content = left_h - 2
    else:
        lw = min(60, max(38, width * 40 // 100))
        rw = width - lw - 2
        left_h = right_h = top
        content = top - 2
    groups={0:'motor e identidad',2:'procedimientos',5:'información',8:'crear'} if S['view']=='plan' else {0:'vistas del cerebro'}
    structured=[]; anchors={}
    for i,(_,label) in enumerate(menu):
        if i in groups:
            if structured: structured.append('')
            title=groups[i]
            structured.append(K['DIM']+title+' '+('─'*max(0,lw-6-api.HL.vis(title)))+K['R'])
        anchors[i]=len(structured)
        prefix='%s %02d  ' % ('›' if i==cursor and not S.get('map_focus') else ' ',i+1)
        ink=K['C']+K['BO'] if i==cursor and not S.get('map_focus') else K['WH']
        structured.append(ink+prefix+api.HL.clip(label,max(1,lw-4-api.HL.vis(prefix)))+K['R'])
    # Scroll by rows (headers and whitespace count) so focus is never hidden.
    start=max(0,min(anchors[cursor]-content//2,len(structured)-content))
    controls=structured[start:start+content]
    explored, remaining = onboarding(S)
    left_title='VISTAS DEL CEREBRO' if S['view']=='brain' else 'CONFIGURA · PASO 2/4'
    left=api.HL.full_box(left_title,controls,K,lw,left_h-2,True,border=K['C'])
    action = menu[cursor][0]
    if S['view'] == 'brain' or S.get('map_focus'):
        route = action.split(':',1)[1] if action.startswith('route:') else S.get('brain_route','setup')
        S['brain_route'] = route
        heading, lead, explanation = brain_view.ROUTES[route][:3]
        enter = 'Volver a configurar' if S.get('map_focus') else ('Volver al plan' if action == 'back' else 'Ver esta ruta')
    else:
        heading, lead, explanation, enter = _PLAN_GUIDE[action]
    center = lambda text: ' ' * max(0,(rw-4-api.HL.vis(text))//2) + text
    viewing=S['view']=='brain' or S.get('map_focus')
    value=brain_view.ROUTES[S.get('brain_route','setup')][0] if viewing else menu[cursor][1]
    impact=explanation+"\n\n"+_PLAN_EXPLANATIONS.get(action, "")
    if viewing:
        impact=_ROUTE_EXPLANATIONS.get(S.get("brain_route","setup"),lead)
    def divider(label):
        return K['DIM']+'─ '+label+K['R']
    right=[K['C']+K['BO']+heading+K['R'],'',divider('tu elección'),
           K['WH']+K['BO']+api.HL.clip(value,rw-4)+K['R'],'',divider('qué cambia')]
    for paragraph in impact.split('\n\n'):
        if right[-1] != divider('qué cambia'): right.append('')
        right += [K['WH']+part+K['R'] for part in api._wrap(paragraph,max(8,rw-6))]
    if viewing:
        right += [K['DIM']+part+K['R'] for part in api._wrap(explanation,max(8,rw-6))]
        if S.get('map_focus'):
            right += ['',K['DIM']+'←→ cambia vista · sólo información'+K['R']]
    right += ['',divider('siguiente paso'),K['OK']+K['BO']+'ENTER · '+enter+K['R']]
    # ←→ recorre explicación conservando el título de la elección.
    capacity = right_h - 2
    offset = min(S.get('detail_scroll', 0), max(0, len(right) - capacity))
    S['detail_scroll'] = offset
    detail = api.HL.full_box('COMPRENDE TU ELECCIÓN', [right[0]] + right[1 + offset:1 + offset + capacity - 1], K, rw, capacity, border=K['B2'], label=K['B'] + K['BO'])
    result = []
    if stacked:
        result = [' ' + line for line in left + detail]
    else:
        result = [' ' + api.HL.pad(a, lw) + '  ' + b for a, b in zip(left, detail)]
    result += ['']
    result += [' ' + line for line in overview_panel(S, api, K, width, bottom)]
    return result[:avail]
